"""Input / output data models for TradingView backtests."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


def _parse_iso_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    # Accept YYYY-MM-DD or full ISO datetime
    if "T" in text:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    return date.fromisoformat(text)


class LoginCredentials(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class CredentialsConfig(BaseModel):
    """Static account / browser settings (reuse across many backtests)."""

    login: LoginCredentials
    storage_state_path: Path = Path("data/tradingview_login.json")
    user_data_dir: Path = Path("data/browser_profile")
    headless: bool = False
    timeout_ms: int = Field(default=60_000, ge=1_000)
    diagnostics_dir: Path = Path("screenshots")

    @field_validator("storage_state_path", "user_data_dir", "diagnostics_dir", mode="before")
    @classmethod
    def coerce_path(cls, value: Any) -> Path:
        return Path(value)


class BacktestDateRange(BaseModel):
    start: date
    end: date

    @field_validator("start", "end", mode="before")
    @classmethod
    def coerce_date(cls, value: Any) -> date:
        return _parse_iso_date(value)

    @model_validator(mode="after")
    def validate_order(self) -> BacktestDateRange:
        if self.end < self.start:
            raise ValueError("backtest.end must be on or after backtest.start")
        return self


class RunConfig(BaseModel):
    """Per-run backtest parameters (CLI flags / function kwargs, not a JSON file)."""

    pine_script_path: Path
    symbol: str = Field(..., min_length=1)
    timeframe: str = Field(..., min_length=1)
    backtest: BacktestDateRange

    @field_validator("pine_script_path", mode="before")
    @classmethod
    def coerce_path(cls, value: Any) -> Path:
        return Path(value)

    @field_validator("symbol", "timeframe")
    @classmethod
    def strip_nonempty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class BacktestConfig(BaseModel):
    """Merged runtime config used by the Playwright pipeline."""

    login: LoginCredentials
    pine_script_path: Path
    symbol: str = Field(..., min_length=1)
    timeframe: str = Field(..., min_length=1)
    backtest: BacktestDateRange
    storage_state_path: Path = Path("data/tradingview_login.json")
    user_data_dir: Path = Path("data/browser_profile")
    headless: bool = False
    timeout_ms: int = Field(default=60_000, ge=1_000)
    diagnostics_dir: Path = Path("screenshots")

    @field_validator(
        "pine_script_path",
        "storage_state_path",
        "user_data_dir",
        "diagnostics_dir",
        mode="before",
    )
    @classmethod
    def coerce_path(cls, value: Any) -> Path:
        return Path(value)

    @field_validator("symbol", "timeframe")
    @classmethod
    def strip_nonempty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @classmethod
    def merge(cls, credentials: CredentialsConfig, run: RunConfig) -> BacktestConfig:
        return cls(
            login=credentials.login,
            pine_script_path=run.pine_script_path,
            symbol=run.symbol,
            timeframe=run.timeframe,
            backtest=run.backtest,
            storage_state_path=credentials.storage_state_path,
            user_data_dir=credentials.user_data_dir,
            headless=credentials.headless,
            timeout_ms=credentials.timeout_ms,
            diagnostics_dir=credentials.diagnostics_dir,
        )

    def resolve_pine_script(self) -> Path:
        path = self.pine_script_path.expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Pine script not found: {path}")
        return path

    def chart_url(self, chart_id: str) -> str:
        from urllib.parse import quote

        return (
            f"https://www.tradingview.com/chart/{chart_id}/"
            f"?symbol={quote(self.symbol, safe='')}"
        )


class StrategyReportData(BaseModel):
    """Extracted Strategy Tester overview + trades list."""

    message: str
    key_factors: dict[str, Any] | None = None
    trades: list[dict[str, Any]] = Field(default_factory=list)
    initial_capital: str | None = None


class BacktestResult(BaseModel):
    """Output from a successful backtest run."""

    message: str
    key_factors: dict[str, Any] | None = None
    trades: list[dict[str, Any]] = Field(default_factory=list)
    symbol: str
    timeframe: str
    backtest_start: date
    backtest_end: date
    initial_capital: str | None = None
    reused_session: bool = False

    def to_stdout_dict(self) -> dict[str, Any]:
        """Serialize for CLI stdout (no credentials)."""
        return {
            "message": self.message,
            "key_factors": self.key_factors,
            "trades": self.trades,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "backtest": {
                "start": self.backtest_start.isoformat(),
                "end": self.backtest_end.isoformat(),
                "initial_capital": self.initial_capital,
            },
            "reused_session": self.reused_session,
        }
