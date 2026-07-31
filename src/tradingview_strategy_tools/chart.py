"""Chart navigation: symbol URL, timeframe selection."""

from __future__ import annotations

import re

from playwright.sync_api import Page

from tradingview_strategy_tools.browser import capture_diagnostics
from tradingview_strategy_tools.exceptions import ChartInteractionError
from tradingview_strategy_tools.models import BacktestConfig
from tradingview_strategy_tools.selectors import SELECTORS

_CHART_BASE_URL = "https://www.tradingview.com/chart"
_CHART_ID_URL = re.compile(r".*/chart/([^/?#]+)")


def _wait_for_chart_id(page: Page, timeout_ms: int) -> str:
    """Wait until TradingView redirects /chart → /chart/<id>, then return that id."""
    page.wait_for_url(_CHART_ID_URL, timeout=timeout_ms)
    match = _CHART_ID_URL.search(page.url)
    if not match:
        raise RuntimeError(f"Chart redirect did not include a chart id: {page.url!r}")
    return match.group(1)


def ensure_single_chart_layout(page: Page, config: BacktestConfig) -> None:
    """If multiple chart panes are open, switch to the first (single) layout."""
    containers = page.locator(SELECTORS.chart_container)
    containers.first.wait_for(state="visible", timeout=config.timeout_ms)
    count = containers.count()
    if count <= 1:
        return

    page.locator(SELECTORS.layouts_button).click()
    single = page.locator(SELECTORS.layout_single_button).first
    single.wait_for(state="visible", timeout=config.timeout_ms)
    single.click()
    page.wait_for_function(
        f"() => document.querySelectorAll('div.chart-container').length < {count}",
        timeout=config.timeout_ms,
    )


def open_chart(page: Page, config: BacktestConfig) -> None:
    """Open /chart, follow redirect to a chart id, then load the requested symbol."""
    try:
        page.goto(_CHART_BASE_URL, wait_until="domcontentloaded")
        chart_id = _wait_for_chart_id(page, config.timeout_ms)
        page.goto(config.chart_url(chart_id), wait_until="domcontentloaded")
        ensure_single_chart_layout(page, config)
        # Allow chart widgets to hydrate
        page.wait_for_timeout(1_500)
    except Exception as exc:
        shot = capture_diagnostics(page, config.diagnostics_dir, "open_chart")
        raise ChartInteractionError(
            f"Failed to open chart for symbol={config.symbol!r}: {exc}",
            screenshot_path=shot,
        ) from exc


def clear_chart_indicators(page: Page, config: BacktestConfig) -> None:
    """Remove all indicators and strategies currently on the chart legend."""
    try:
        closed = page.locator(SELECTORS.object_tree_closed)
        if closed.count() > 0:
            toggler = page.locator(SELECTORS.object_tree_toggler)
            toggler.first.wait_for(state="visible", timeout=config.timeout_ms)
            toggler.first.click()
            page.wait_for_timeout(300)

        titles = page.locator(SELECTORS.legend_titles)
        # Hover reveals delete; delete one-by-one as DOM shrinks after each click
        while titles.count() > 0:
            titles.first.hover()
            delete_btn = page.locator(SELECTORS.legend_delete_action).first
            delete_btn.wait_for(state="visible", timeout=config.timeout_ms)
            delete_btn.click()
            page.wait_for_timeout(200)
    except Exception as exc:
        shot = capture_diagnostics(page, config.diagnostics_dir, "clear_chart_indicators")
        raise ChartInteractionError(
            f"Failed to clear chart indicators: {exc}",
            screenshot_path=shot,
        ) from exc


def set_timeframe(page: Page, config: BacktestConfig) -> None:
    """
    Set the chart interval.

    Click Change interval → fill the interval input → Enter.
    Selectors live in selectors.py — adjust there if TradingView UI changes.
    """
    tf = config.timeframe
    try:
        button = page.locator(SELECTORS.timeframe_button)
        button.first.wait_for(state="visible", timeout=config.timeout_ms)
        button.first.click()

        interval_input = page.locator(SELECTORS.timeframe_input)
        interval_input.first.wait_for(state="visible", timeout=config.timeout_ms)
        interval_input.first.fill(tf)
        page.keyboard.press("Enter")

        page.wait_for_timeout(800)
    except ChartInteractionError:
        raise
    except Exception as exc:
        shot = capture_diagnostics(page, config.diagnostics_dir, "set_timeframe")
        raise ChartInteractionError(
            f"Failed to set timeframe={tf!r}: {exc}",
            screenshot_path=shot,
        ) from exc


def prepare_chart(page: Page, config: BacktestConfig) -> None:
    """Open chart URL, clear existing indicators/strategies, apply timeframe."""
    open_chart(page, config)
    clear_chart_indicators(page, config)
    set_timeframe(page, config)
