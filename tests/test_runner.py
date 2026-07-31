"""Runner orchestration tests with mocked TradingView steps."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tradingview_strategy_tools.cli import main
from tradingview_strategy_tools.models import (
    BacktestResult,
    CredentialsConfig,
    StrategyReportData,
)
from tradingview_strategy_tools.runner import run_backtest


def _write_credentials(tmp_path: Path) -> tuple[Path, Path]:
    pine = tmp_path / "s.pine"
    pine.write_text("//@version=5\nstrategy('t')\n", encoding="utf-8")

    credentials_path = tmp_path / "credentials.json"
    credentials_path.write_text(
        json.dumps(
            {
                "login": {"username": "u@example.com", "password": "secret"},
                "storage_state_path": str(tmp_path / "tradingview_login.json"),
                "diagnostics_dir": str(tmp_path / "shots"),
            }
        ),
        encoding="utf-8",
    )
    return credentials_path, pine


def _cli_args(credentials_path: Path, pine: Path) -> list[str]:
    return [
        str(credentials_path),
        "--pine",
        str(pine),
        "--symbol",
        "NASDAQ:AAPL",
        "--timeframe",
        "1D",
        "--start",
        "2024-01-01",
        "--end",
        "2024-06-30",
    ]


def test_run_backtest_order_and_result(tmp_path: Path) -> None:
    pine = tmp_path / "s.pine"
    pine.write_text("//@version=5\nstrategy('t')\n", encoding="utf-8")
    credentials = CredentialsConfig.model_validate(
        {
            "login": {"username": "u@example.com", "password": "secret"},
            "storage_state_path": str(tmp_path / "tradingview_login.json"),
        }
    )

    session = MagicMock()
    session.page = MagicMock()
    order: list[str] = []

    class _Ctx:
        def __enter__(self):
            order.append("browser")
            return session

        def __exit__(self, *args):
            return False

    with (
        patch("tradingview_strategy_tools.runner.browser_session", return_value=_Ctx()),
        patch(
            "tradingview_strategy_tools.runner.ensure_authenticated",
            side_effect=lambda *a, **k: (order.append("auth") or True),
        ),
        patch(
            "tradingview_strategy_tools.runner.prepare_chart",
            side_effect=lambda *a, **k: order.append("chart"),
        ),
        patch(
            "tradingview_strategy_tools.runner.load_and_apply_pine",
            side_effect=lambda *a, **k: (order.append("pine") or "src"),
        ),
        patch(
            "tradingview_strategy_tools.runner.run_deep_backtest_and_report",
            side_effect=lambda *a, **k: (
                order.append("report")
                or StrategyReportData(
                    message="success",
                    key_factors={
                        "total_pnl": {"value": "+10 USD", "percentage": "+1%"},
                        "profit_factor": 1.5,
                    },
                    trades=[{"Trade number": 1, "Type": "Entry long"}],
                    initial_capital="10,000 USD",
                )
            ),
        ),
    ):
        result = run_backtest(
            credentials=credentials,
            pine_script_path=pine,
            symbol="NASDAQ:AAPL",
            timeframe="1D",
            start="2024-01-01",
            end="2024-06-30",
        )

    assert order == ["browser", "auth", "chart", "pine", "report"]
    assert result.message == "success"
    assert result.key_factors == {
        "total_pnl": {"value": "+10 USD", "percentage": "+1%"},
        "profit_factor": 1.5,
    }
    assert result.trades == [{"Trade number": 1, "Type": "Entry long"}]
    assert result.reused_session is True
    assert result.symbol == "NASDAQ:AAPL"
    assert result.backtest_start == date(2024, 1, 1)
    assert result.initial_capital == "10,000 USD"


def test_cli_prints_json_without_password(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    credentials_path, pine = _write_credentials(tmp_path)
    fake = BacktestResult(
        message="success",
        key_factors={"profit_factor": 1.89},
        trades=[],
        symbol="NASDAQ:AAPL",
        timeframe="1D",
        backtest_start=date(2024, 1, 1),
        backtest_end=date(2024, 6, 30),
        initial_capital="10,000 USD",
        reused_session=False,
    )
    with patch("tradingview_strategy_tools.cli.run_backtest", return_value=fake):
        code = main(_cli_args(credentials_path, pine))

    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["message"] == "success"
    assert payload["key_factors"] == {"profit_factor": 1.89}
    assert payload["trades"] == []
    assert payload["backtest"]["initial_capital"] == "10,000 USD"
    assert "password" not in out
    assert "secret" not in out


def test_cli_missing_credentials(tmp_path: Path) -> None:
    pine = tmp_path / "s.pine"
    pine.write_text("//@version=5\nstrategy('t')\n", encoding="utf-8")
    code = main(_cli_args(tmp_path / "missing-creds.json", pine))
    assert code == 2


def test_read_pine_script(tmp_path: Path) -> None:
    from tradingview_strategy_tools.pine import read_pine_script

    pine = tmp_path / "x.pine"
    pine.write_text("// hello\n", encoding="utf-8")
    assert "hello" in read_pine_script(pine)
