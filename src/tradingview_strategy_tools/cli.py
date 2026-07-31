"""CLI entry point: tradingview-backtest <credentials.json> --pine ... --symbol ..."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tradingview_strategy_tools.exceptions import TradingViewError
from tradingview_strategy_tools.models import CredentialsConfig, RunConfig
from tradingview_strategy_tools.runner import run_backtest


def _load_credentials(path: Path) -> CredentialsConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return CredentialsConfig.model_validate(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tradingview-backtest",
        description=(
            "Run a TradingView Pine strategy backtest via Playwright. "
            "Static login settings come from credentials JSON; "
            "pine/symbol/timeframe/dates are CLI parameters."
        ),
    )
    parser.add_argument(
        "credentials",
        type=Path,
        help="Static credentials JSON (see credentials.example.json)",
    )
    parser.add_argument(
        "--pine",
        required=True,
        type=Path,
        help="Path to the Pine Script (.pine) file",
    )
    parser.add_argument(
        "--symbol",
        required=True,
        help="TradingView symbol, e.g. NASDAQ:AAPL",
    )
    parser.add_argument(
        "--timeframe",
        required=True,
        help="Chart timeframe, e.g. 1D, 60, 4h",
    )
    parser.add_argument(
        "--start",
        required=True,
        help="Deep Backtesting start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        required=True,
        help="Deep Backtesting end date (YYYY-MM-DD)",
    )
    args = parser.parse_args(argv)

    if not args.credentials.is_file():
        print(f"Credentials file not found: {args.credentials}", file=sys.stderr)
        return 2

    try:
        credentials = _load_credentials(args.credentials)
        run = RunConfig.model_validate(
            {
                "pine_script_path": args.pine,
                "symbol": args.symbol,
                "timeframe": args.timeframe,
                "backtest": {"start": args.start, "end": args.end},
            }
        )
        result = run_backtest(credentials=credentials, run=run)
    except TradingViewError as exc:
        print(f"TradingView error: {exc}", file=sys.stderr)
        if exc.screenshot_path:
            print(f"Screenshot: {exc.screenshot_path}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 ??surface validation / IO clearly
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result.to_stdout_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
