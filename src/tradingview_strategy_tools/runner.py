"""Orchestrate auth → chart → pine → deep backtest → report."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from tradingview_strategy_tools.auth import ensure_authenticated
from tradingview_strategy_tools.browser import browser_session, capture_diagnostics
from tradingview_strategy_tools.chart import prepare_chart
from tradingview_strategy_tools.exceptions import TradingViewError
from tradingview_strategy_tools.models import (
    BacktestConfig,
    BacktestResult,
    CredentialsConfig,
    RunConfig,
)
from tradingview_strategy_tools.pine import load_and_apply_pine
from tradingview_strategy_tools.report import run_deep_backtest_and_report


def run_backtest(
    config: BacktestConfig | None = None,
    *,
    credentials: CredentialsConfig | None = None,
    run: RunConfig | None = None,
    pine_script_path: str | Path | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
    start: str | date | None = None,
    end: str | date | None = None,
) -> BacktestResult:
    """
    Synchronously run a TradingView strategy backtest.

    Provide either:
    - ``config`` (merged), or
    - ``credentials`` + ``run``, or
    - ``credentials`` + individual parameters
      (``pine_script_path``, ``symbol``, ``timeframe``, ``start``, ``end``).

    Reuses ``storage_state`` when valid to avoid logging in too often.
    """
    if config is None:
        if credentials is None:
            raise TypeError("Provide config=... or credentials=... with run parameters")
        if run is None:
            missing = [
                name
                for name, value in (
                    ("pine_script_path", pine_script_path),
                    ("symbol", symbol),
                    ("timeframe", timeframe),
                    ("start", start),
                    ("end", end),
                )
                if value is None
            ]
            if missing:
                raise TypeError(
                    "Provide run=... or all of pine_script_path, symbol, "
                    f"timeframe, start, end (missing: {', '.join(missing)})"
                )
            run = RunConfig.model_validate(
                {
                    "pine_script_path": pine_script_path,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "backtest": {"start": start, "end": end},
                }
            )
        config = BacktestConfig.merge(credentials, run)
    elif (
        credentials is not None
        or run is not None
        or pine_script_path is not None
        or symbol is not None
        or timeframe is not None
        or start is not None
        or end is not None
    ):
        raise TypeError("Pass either config=... or credentials=+parameters, not both")

    # Fail fast on missing pine file before launching browser
    config.resolve_pine_script()

    with browser_session(config) as session:
        try:
            reused = ensure_authenticated(session, config)
            prepare_chart(session.page, config)
            load_and_apply_pine(session.page, config)
            report = run_deep_backtest_and_report(session.page, config)
        except TradingViewError:
            raise
        except Exception as exc:
            shot = capture_diagnostics(session.page, config.diagnostics_dir, "runner")
            raise TradingViewError(
                f"Unexpected failure during backtest: {exc}",
                screenshot_path=shot,
            ) from exc

    return BacktestResult(
        message=report.message,
        key_factors=report.key_factors,
        trades=report.trades,
        symbol=config.symbol,
        timeframe=config.timeframe,
        backtest_start=config.backtest.start,
        backtest_end=config.backtest.end,
        initial_capital=report.initial_capital,
        reused_session=reused,
    )
