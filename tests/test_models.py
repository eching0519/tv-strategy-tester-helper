"""Unit tests for CredentialsConfig / RunConfig / BacktestConfig."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from tradingview_strategy_tools.models import (
    BacktestConfig,
    BacktestResult,
    CredentialsConfig,
    RunConfig,
)


def _credentials_payload(tmp_path: Path, **overrides) -> dict:
    data = {
        "login": {"username": "u@example.com", "password": "secret"},
        "storage_state_path": str(tmp_path / "tradingview_login.json"),
    }
    data.update(overrides)
    return data


def _run_payload(tmp_path: Path, **overrides) -> dict:
    pine = tmp_path / "s.pine"
    if not pine.exists():
        pine.write_text("//@version=5\nstrategy('t')\n", encoding="utf-8")
    data = {
        "pine_script_path": str(pine),
        "symbol": "NASDAQ:AAPL",
        "timeframe": "1D",
        "backtest": {"start": "2024-01-01", "end": "2024-06-30"},
    }
    data.update(overrides)
    return data


def test_credentials_defaults(tmp_path: Path) -> None:
    creds = CredentialsConfig.model_validate(_credentials_payload(tmp_path))
    assert creds.headless is False
    assert creds.timeout_ms == 60_000
    assert creds.login.username == "u@example.com"


def test_run_parse_iso_dates(tmp_path: Path) -> None:
    run = RunConfig.model_validate(_run_payload(tmp_path))
    assert run.backtest.start == date(2024, 1, 1)
    assert run.backtest.end == date(2024, 6, 30)
    assert run.symbol == "NASDAQ:AAPL"


def test_rejects_inverted_date_range(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        RunConfig.model_validate(
            _run_payload(
                tmp_path,
                backtest={"start": "2024-12-31", "end": "2024-01-01"},
            )
        )


def test_merge_keeps_layers_separate(tmp_path: Path) -> None:
    creds = CredentialsConfig.model_validate(_credentials_payload(tmp_path))
    run = RunConfig.model_validate(
        _run_payload(tmp_path, symbol="BINANCE:BTCUSDT", timeframe="60")
    )
    cfg = BacktestConfig.merge(creds, run)
    assert cfg.login.username == "u@example.com"
    assert cfg.symbol == "BINANCE:BTCUSDT"
    assert cfg.timeframe == "60"
    assert "symbol=BINANCE%3ABTCUSDT" in cfg.chart_url("abc123")
    assert "/chart/abc123/" in cfg.chart_url("abc123")


def test_resolve_pine_missing(tmp_path: Path) -> None:
    creds = CredentialsConfig.model_validate(_credentials_payload(tmp_path))
    run = RunConfig.model_validate(
        _run_payload(tmp_path, pine_script_path=str(tmp_path / "missing.pine"))
    )
    cfg = BacktestConfig.merge(creds, run)
    with pytest.raises(FileNotFoundError):
        cfg.resolve_pine_script()


def test_result_stdout_hides_credentials() -> None:
    result = BacktestResult(
        message="success",
        key_factors={
            "total_pnl": {"value": "+10 USD", "percentage": "+1%"},
            "profit_factor": 1.5,
        },
        trades=[{"Trade number": 1, "Type": "Entry long"}],
        symbol="NASDAQ:AAPL",
        timeframe="1D",
        backtest_start=date(2024, 1, 1),
        backtest_end=date(2024, 6, 30),
        initial_capital="10,000 USD",
        reused_session=True,
    )
    payload = result.to_stdout_dict()
    assert "password" not in payload
    assert "login" not in payload
    assert payload["message"] == "success"
    assert payload["key_factors"] == {
        "total_pnl": {"value": "+10 USD", "percentage": "+1%"},
        "profit_factor": 1.5,
    }
    assert payload["trades"] == [{"Trade number": 1, "Type": "Entry long"}]
    assert payload["reused_session"] is True
    assert payload["backtest"]["start"] == "2024-01-01"
    assert payload["backtest"]["initial_capital"] == "10,000 USD"


def test_result_no_trades_stdout() -> None:
    result = BacktestResult(
        message="success, but no trades",
        key_factors=None,
        trades=[],
        symbol="NASDAQ:AAPL",
        timeframe="1D",
        backtest_start=date(2024, 1, 1),
        backtest_end=date(2024, 6, 30),
    )
    payload = result.to_stdout_dict()
    assert payload["message"].startswith("success, but")
    assert payload["key_factors"] is None
    assert payload["trades"] == []
