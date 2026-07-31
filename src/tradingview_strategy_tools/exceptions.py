"""Domain exceptions for TradingView automation."""

from __future__ import annotations

from pathlib import Path


class TradingViewError(Exception):
    """Base error for TradingView automation failures."""

    def __init__(self, message: str, *, screenshot_path: Path | None = None) -> None:
        super().__init__(message)
        self.screenshot_path = screenshot_path


class AuthenticationError(TradingViewError):
    """Login failed or session could not be established."""


class ChartInteractionError(TradingViewError):
    """Opening chart, setting symbol/timeframe, or related UI failed."""


class PineEditorError(TradingViewError):
    """Reading or applying Pine Script failed."""


class DeepBacktestError(TradingViewError):
    """Deep Backtesting date range / run failed."""


class ReportExtractionError(TradingViewError):
    """Strategy report could not be read."""
