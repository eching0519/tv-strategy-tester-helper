"""Auth + storage_state behaviour with mocked Playwright pages."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tradingview_strategy_tools.auth import ensure_authenticated, is_logged_in
from tradingview_strategy_tools.browser import apply_storage_state_cookies, save_storage_state
from tradingview_strategy_tools.exceptions import AuthenticationError
from tradingview_strategy_tools.models import BacktestConfig


def _config(tmp_path: Path) -> BacktestConfig:
    pine = tmp_path / "s.pine"
    pine.write_text("//@version=5\nstrategy('t')\n", encoding="utf-8")
    return BacktestConfig.model_validate(
        {
            "login": {"username": "u@example.com", "password": "secret"},
            "pine_script_path": str(pine),
            "symbol": "NASDAQ:AAPL",
            "timeframe": "1D",
            "backtest": {"start": "2024-01-01", "end": "2024-06-30"},
            "storage_state_path": str(tmp_path / "tradingview_login.json"),
            "diagnostics_dir": str(tmp_path / "shots"),
            "timeout_ms": 5_000,
        }
    )


def test_is_logged_in_via_session_cookie() -> None:
    page = MagicMock()
    page.context.cookies.return_value = [{"name": "sessionid", "value": "abc"}]
    assert is_logged_in(page) is True


def test_is_logged_in_false_without_session() -> None:
    page = MagicMock()
    page.context.cookies.return_value = [{"name": "tv_ecuid", "value": "x"}]
    assert is_logged_in(page) is False


def test_save_storage_state_atomic(tmp_path: Path) -> None:
    target = tmp_path / "data" / "tradingview_login.json"
    context = MagicMock()

    def _write(path: str) -> None:
        Path(path).write_text('{"cookies":[]}', encoding="utf-8")

    context.storage_state.side_effect = lambda path: _write(path)
    save_storage_state(context, target)
    assert target.is_file()
    assert target.read_text(encoding="utf-8") == '{"cookies":[]}'
    assert not list(target.parent.glob("*.tmp"))


def test_apply_storage_state_cookies(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        '{"cookies":[{"name":"sessionid","value":"abc","domain":".tradingview.com","path":"/"}]}',
        encoding="utf-8",
    )
    context = MagicMock()
    assert apply_storage_state_cookies(context, path) is True
    context.add_cookies.assert_called_once()
    assert apply_storage_state_cookies(context, tmp_path / "missing.json") is False

def test_ensure_authenticated_reuses_valid_session(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    cfg.storage_state_path.write_text("{}", encoding="utf-8")

    session = MagicMock()
    session.used_existing_state = True
    session.page = MagicMock()
    session.page.goto = MagicMock()
    session.storage_state_path = cfg.storage_state_path

    with patch("tradingview_strategy_tools.auth.is_logged_in", return_value=True):
        reused = ensure_authenticated(session, cfg)

    assert reused is True
    session.page.goto.assert_called_once()


def test_ensure_authenticated_logs_in_once_when_invalid(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    session = MagicMock()
    session.used_existing_state = False
    session.page = MagicMock()
    session.page.goto = MagicMock()
    session.context = MagicMock()
    session.storage_state_path = cfg.storage_state_path

    login_calls = {"n": 0}

    def fake_login(*_a, **_k) -> None:
        login_calls["n"] += 1

    with (
        # Not logged in before password login; logged in after
        patch(
            "tradingview_strategy_tools.auth.is_logged_in",
            side_effect=[False, True],
        ),
        patch("tradingview_strategy_tools.auth._login_once", side_effect=fake_login),
        patch("tradingview_strategy_tools.auth.save_storage_state") as save_mock,
    ):
        reused = ensure_authenticated(session, cfg)

    assert reused is False
    assert login_calls["n"] == 1
    save_mock.assert_called_once()


def test_ensure_authenticated_reuses_profile_without_storage_file(tmp_path: Path) -> None:
    """Persistent profile cookies alone should skip password login."""
    cfg = _config(tmp_path)
    session = MagicMock()
    session.used_existing_state = False
    session.page = MagicMock()
    session.page.goto = MagicMock()
    session.storage_state_path = cfg.storage_state_path

    with (
        patch("tradingview_strategy_tools.auth.is_logged_in", return_value=True),
        patch("tradingview_strategy_tools.auth._login_once") as login_mock,
    ):
        reused = ensure_authenticated(session, cfg)

    assert reused is True
    login_mock.assert_not_called()


def test_ensure_authenticated_raises_when_login_fails(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    session = MagicMock()
    session.used_existing_state = False
    session.page = MagicMock()
    session.page.goto = MagicMock()
    session.storage_state_path = cfg.storage_state_path

    with (
        patch("tradingview_strategy_tools.auth.is_logged_in", return_value=False),
        patch("tradingview_strategy_tools.auth._login_once"),
        patch(
            "tradingview_strategy_tools.auth.capture_diagnostics",
            return_value=tmp_path / "fail.png",
        ),
    ):
        with pytest.raises(AuthenticationError):
            ensure_authenticated(session, cfg)
