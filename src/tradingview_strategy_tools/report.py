"""Strategy Tester date range and report extraction."""

from __future__ import annotations

import csv
import io
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tradingview_strategy_tools.browser import capture_diagnostics
from tradingview_strategy_tools.exceptions import (DeepBacktestError,
                                                   ReportExtractionError)
from tradingview_strategy_tools.models import (BacktestConfig,
                                               StrategyReportData)
from tradingview_strategy_tools.selectors import SELECTORS

_EMPTY_REPORT_TITLE = "This report requires trade data"
_REPORT_UPDATED_SNACKBAR = "The report has been updated successfully"
_REPORT_UPDATED_TIMEOUT_MS = 120_000
_NO_TRADES_MESSAGE = (
    "success, but this strategy did not make any trades in the selected period "
    "(TradingView: 'This report requires trade data'). "
    "Modify the strategy so it generates trades, or adjust the backtest date range."
)
_SUCCESS_MESSAGE = "success"


def _format_tv_date(d: date) -> str:
    """TradingView date inputs use YYYY-MM-DD."""
    return d.isoformat()


_SNACKBAR_IS_UPDATED_JS = """([sel, expected]) => {
    const el = document.querySelector(sel);
    return !!el && (el.innerText || '').trim() === expected;
}"""

_SNACKBAR_NOT_UPDATED_JS = """([sel, expected]) => {
    const el = document.querySelector(sel);
    return !el || (el.innerText || '').trim() !== expected;
}"""

# Initial load after Pine: snackbar may already be gone — also accept report UI.
_REPORT_READY_JS = """([snackbarSel, expected, capitalSel, keyFactsSel, emptySel]) => {
    const el = document.querySelector(snackbarSel);
    if (el && (el.innerText || '').trim() === expected) return true;
    const visible = (sel) => {
        const n = document.querySelector(sel);
        if (!n) return false;
        const r = n.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };
    return visible(capitalSel) || visible(keyFactsSel) || visible(emptySel);
}"""


def _wait_for_report_updated(
    page: Page,
    *,
    timeout_ms: int = _REPORT_UPDATED_TIMEOUT_MS,
    clear_stale: bool = False,
) -> None:
    """Wait until snackbar shows the report-updated confirmation."""
    arg = [SELECTORS.snackbar_container, _REPORT_UPDATED_SNACKBAR]
    if clear_stale:
        # Avoid matching a leftover toast from the previous update.
        try:
            page.wait_for_function(
                _SNACKBAR_NOT_UPDATED_JS,
                arg=arg,
                timeout=min(timeout_ms, 5_000),
            )
        except PlaywrightTimeoutError:
            pass
    page.wait_for_function(
        _SNACKBAR_IS_UPDATED_JS,
        arg=arg,
        timeout=timeout_ms,
    )


def _wait_for_report_ready(page: Page, timeout_ms: int = _REPORT_UPDATED_TIMEOUT_MS) -> None:
    """Wait until the Strategy Tester report finished its initial load after Pine."""
    page.wait_for_function(
        _REPORT_READY_JS,
        arg=[
            SELECTORS.snackbar_container,
            _REPORT_UPDATED_SNACKBAR,
            SELECTORS.strategy_initial_capital,
            SELECTORS.strategy_key_facts,
            SELECTORS.strategy_report_empty_title,
        ],
        timeout=timeout_ms,
    )


def _open_date_range_preset_popup(page: Page, timeout_ms: int) -> None:
    """Click date-range menu until the preset popup is visible."""
    menu = page.locator(SELECTORS.date_range_menu).first
    menu.wait_for(state="visible", timeout=timeout_ms)
    popup = page.locator(SELECTORS.date_range_preset_popup).first
    last_exc: Exception | None = None
    for _ in range(3):
        try:
            menu.click(timeout=5_000)
        except PlaywrightTimeoutError as exc:
            last_exc = exc
            # Covered / unstable target — bypass actionability checks.
            menu.click(force=True, timeout=5_000)
        try:
            popup.wait_for(state="visible", timeout=5_000)
            return
        except PlaywrightTimeoutError as exc:
            last_exc = exc
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
    raise DeepBacktestError(
        f"Date-range preset popup did not open after clicking menu: {last_exc}"
    )


def strategy_tester_is_open(page: Page) -> bool:
    """True when the Strategy Tester date-range menu button is present and visible."""
    menu = page.locator(SELECTORS.date_range_menu)
    try:
        return menu.count() > 0 and menu.first.is_visible()
    except PlaywrightTimeoutError:
        return False


def open_strategy_tester(page: Page, config: BacktestConfig) -> None:
    try:
        if not strategy_tester_is_open(page):
            tab = page.locator(SELECTORS.strategy_tester_tab)
            tab.first.wait_for(state="visible", timeout=config.timeout_ms)
            tab.first.click()
        page.locator(SELECTORS.date_range_menu).first.wait_for(
            state="visible",
            timeout=config.timeout_ms,
        )
        # Do not click date-range until the post-Pine report has settled.
        _wait_for_report_ready(page, _REPORT_UPDATED_TIMEOUT_MS)
    except Exception as exc:
        shot = capture_diagnostics(page, config.diagnostics_dir, "open_strategy_tester")
        raise DeepBacktestError(
            f"Could not open Strategy Tester: {exc}",
            screenshot_path=shot,
        ) from exc


def set_deep_backtest_dates(page: Page, config: BacktestConfig) -> None:
    start = _format_tv_date(config.backtest.start)
    end = _format_tv_date(config.backtest.end)
    try:
        _open_date_range_preset_popup(page, config.timeout_ms)

        presets = page.locator(SELECTORS.date_range_preset_button)
        presets.last.wait_for(state="visible", timeout=config.timeout_ms)
        page.wait_for_timeout(300)
        presets.last.click()

        # Custom date-range dialog
        dialog = page.locator(SELECTORS.date_range_dialog)
        dialog.first.wait_for(state="visible", timeout=config.timeout_ms)
        inputs = page.locator(SELECTORS.date_range_input)
        inputs.nth(0).wait_for(state="visible", timeout=config.timeout_ms)
        inputs.nth(1).wait_for(state="visible", timeout=config.timeout_ms)

        inputs.nth(0).click()
        page.wait_for_timeout(300)
        inputs.nth(0).fill("")
        page.wait_for_timeout(300)
        inputs.nth(0).fill(start)
        page.wait_for_timeout(300)
        inputs.nth(1).click()
        page.wait_for_timeout(300)
        inputs.nth(1).fill("")
        page.wait_for_timeout(300)
        inputs.nth(1).fill(end)
        page.wait_for_timeout(300)

        submit = page.locator(SELECTORS.date_range_submit)
        submit.first.wait_for(state="visible", timeout=config.timeout_ms)
        submit.first.click()
        page.wait_for_timeout(300)

        _wait_for_report_updated(
            page,
            timeout_ms=_REPORT_UPDATED_TIMEOUT_MS,
            clear_stale=True,
        )
    except Exception as exc:
        if isinstance(exc, DeepBacktestError) and exc.screenshot_path is not None:
            raise
        shot = capture_diagnostics(page, config.diagnostics_dir, "set_deep_dates")
        if isinstance(exc, DeepBacktestError):
            raise DeepBacktestError(str(exc), screenshot_path=shot) from exc
        raise DeepBacktestError(
            f"Failed to set Strategy Tester dates {start} → {end}: {exc}",
            screenshot_path=shot,
        ) from exc


def _report_requires_trade_data(page: Page) -> bool:
    """True when Strategy Tester shows the empty-trades placeholder title."""
    title = page.locator(SELECTORS.strategy_report_empty_title)
    try:
        if title.count() == 0:
            return False
        text = (title.first.inner_text(timeout=2_000) or "").strip()
        return text == _EMPTY_REPORT_TITLE
    except PlaywrightTimeoutError:
        return False


def _coerce_csv_value(value: str) -> Any:
    text = value.strip()
    if text == "":
        return text
    try:
        if "." in text or "e" in text.lower():
            return float(text)
        return int(text)
    except ValueError:
        return text


def parse_trades_csv(csv_text: str) -> list[dict[str, Any]]:
    """Parse TradingView List of Trades CSV into a list of row dicts."""
    text = csv_text.strip()
    if not text:
        return []
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    for raw in reader:
        if not raw or all(not (v or "").strip() for v in raw.values()):
            continue
        rows.append({key: _coerce_csv_value(val or "") for key, val in raw.items() if key})
    return rows


_KEY_FACTOR_TITLE_MAP = {
    "Total PnL": "total_pnl",
    "Max drawdown": "max_drawdown",
    "Profitable trades": "profitable_trades",
    "Profit factor": "profit_factor",
}

_EXTRACT_KEY_FACTOR_CELLS_JS = """
(el) => Array.from(el.querySelectorAll('[class*="containerCell"]')).map((cell) => ({
  title: (cell.querySelector('[class*="title-"]')?.textContent || '').trim(),
  value: (cell.querySelector('[class*="value-"]')?.textContent || '').trim(),
  currency: (cell.querySelector('[class*="currency-"]')?.textContent || '').trim(),
  change: (cell.querySelector('[class*="change-"]')?.textContent || '').trim(),
})).filter((cell) => cell.title)
"""


def _title_to_key(title: str) -> str:
    mapped = _KEY_FACTOR_TITLE_MAP.get(title)
    if mapped:
        return mapped
    return title.strip().lower().replace(" ", "_")


def _combine_value_currency(value: str, currency: str) -> str:
    value = value.strip()
    currency = currency.strip()
    if value and currency:
        return f"{value} {currency}"
    return value or currency


def build_key_factors(cells: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Normalize Strategy Tester key-fact cells into structured JSON."""
    if not cells:
        return None

    result: dict[str, Any] = {}
    for raw in cells:
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        key = _title_to_key(title)
        value = str(raw.get("value") or "").strip()
        currency = str(raw.get("currency") or "").strip()
        change = str(raw.get("change") or "").strip()

        if key == "profit_factor":
            try:
                result[key] = float(value.replace(",", ""))
            except ValueError:
                result[key] = value
            continue

        if key == "profitable_trades":
            # UI shows percentage in value and ratio (e.g. 1/3) in change.
            result[key] = {
                "value": change or value,
                "percentage": value if change else "",
            }
            continue

        result[key] = {
            "value": _combine_value_currency(value, currency),
            "percentage": change,
        }

    return result or None


def _extract_initial_capital(page: Page, timeout_ms: int) -> str | None:
    """Read Strategy Tester initial-capital button text, if present."""
    btn = page.locator(SELECTORS.strategy_initial_capital)
    try:
        btn.first.wait_for(state="visible", timeout=timeout_ms)
        text = (btn.first.inner_text(timeout=timeout_ms) or "").strip()
        return text or None
    except PlaywrightTimeoutError:
        return None


def extract_strategy_report(page: Page, config: BacktestConfig) -> StrategyReportData:
    try:
        initial_capital = _extract_initial_capital(page, config.timeout_ms)

        if _report_requires_trade_data(page):
            capture_diagnostics(page, config.diagnostics_dir, "no_trades")
            return StrategyReportData(
                message=_NO_TRADES_MESSAGE,
                key_factors=None,
                trades=[],
                initial_capital=initial_capital,
            )

        overview_tab = page.locator(SELECTORS.strategy_overview_tab)
        overview_tab.first.wait_for(state="visible", timeout=config.timeout_ms)
        overview_tab.first.click()

        facts = page.locator(SELECTORS.strategy_key_facts)
        facts.first.wait_for(state="visible", timeout=config.timeout_ms)
        cells = facts.first.evaluate(_EXTRACT_KEY_FACTOR_CELLS_JS)
        key_factors = build_key_factors(cells if isinstance(cells, list) else [])

        trades_tab = page.locator(SELECTORS.strategy_list_of_trades_tab)
        trades_tab.first.wait_for(state="visible", timeout=config.timeout_ms)
        trades_tab.first.click()

        download_btn = page.locator(SELECTORS.strategy_download_csv)
        download_btn.first.wait_for(state="visible", timeout=config.timeout_ms)
        with page.expect_download(timeout=config.timeout_ms) as download_info:
            download_btn.first.click()
        download = download_info.value

        tmp_dir = Path(tempfile.mkdtemp(prefix="tv_strategy_csv_"))
        csv_path = tmp_dir / (download.suggested_filename or "trades.csv")
        try:
            download.save_as(str(csv_path))
            csv_text = csv_path.read_text(encoding="utf-8").strip()
        finally:
            if csv_path.exists():
                csv_path.unlink()
            tmp_dir.rmdir()

        trades = parse_trades_csv(csv_text)
        if not key_factors and not trades:
            shot = capture_diagnostics(page, config.diagnostics_dir, "empty_report")
            raise ReportExtractionError(
                "Strategy key factors and CSV were empty.",
                screenshot_path=shot,
            )
        return StrategyReportData(
            message=_SUCCESS_MESSAGE,
            key_factors=key_factors,
            trades=trades,
            initial_capital=initial_capital,
        )
    except ReportExtractionError:
        raise
    except Exception as exc:
        shot = capture_diagnostics(page, config.diagnostics_dir, "extract_report")
        raise ReportExtractionError(
            f"Failed to extract strategy report: {exc}",
            screenshot_path=shot,
        ) from exc


def run_deep_backtest_and_report(page: Page, config: BacktestConfig) -> StrategyReportData:
    open_strategy_tester(page, config)
    set_deep_backtest_dates(page, config)
    return extract_strategy_report(page, config)
