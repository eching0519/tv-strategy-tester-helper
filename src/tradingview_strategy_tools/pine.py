"""Pine Script file loading and Pine Editor interaction."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tradingview_strategy_tools.browser import capture_diagnostics
from tradingview_strategy_tools.exceptions import PineEditorError
from tradingview_strategy_tools.models import BacktestConfig
from tradingview_strategy_tools.selectors import SELECTORS

_PINE_EDITOR_TITLE = re.compile(r"^Pine Editor$")
_KEYBOARD_SETTLE_MS = 300
_PASTE_CHUNK_LINES = 300


def read_pine_script(path: Path) -> str:
    path = path.expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Pine script not found: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise PineEditorError(f"Pine script is empty: {path}")
    return text


def _pine_editor_title(page: Page):
    return page.locator(SELECTORS.pine_editor_title).filter(has_text=_PINE_EDITOR_TITLE)


def pine_editor_is_open(page: Page) -> bool:
    """True when a visible title slot reads exactly 'Pine Editor'."""
    title = _pine_editor_title(page)
    try:
        return title.count() > 0 and title.first.is_visible()
    except PlaywrightTimeoutError:
        return False


def open_pine_editor(page: Page, config: BacktestConfig) -> None:
    try:
        if not pine_editor_is_open(page):
            products = page.locator(SELECTORS.products_button)
            products.first.wait_for(state="visible", timeout=config.timeout_ms)
            products.first.click()

            menuitem = page.locator(SELECTORS.pine_editor_menuitem)
            menuitem.first.wait_for(state="visible", timeout=config.timeout_ms)
            menuitem.first.click()
        _pine_editor_title(page).first.wait_for(
            state="visible",
            timeout=config.timeout_ms,
        )
    except Exception as exc:
        shot = capture_diagnostics(page, config.diagnostics_dir, "open_pine_editor")
        raise PineEditorError(
            f"Could not open Pine Editor: {exc}",
            screenshot_path=shot,
        ) from exc


def create_new_strategy(page: Page, config: BacktestConfig) -> None:
    """Open the Pine title menu and create a blank Strategy script."""
    try:
        title_btn = page.locator(SELECTORS.pine_script_title_button)
        title_btn.first.wait_for(state="visible", timeout=config.timeout_ms)
        title_btn.first.click()

        # Hover "New" submenu to reveal Strategy
        new_menu = page.locator(SELECTORS.pine_new_menu_button)
        new_menu.first.wait_for(state="visible", timeout=config.timeout_ms)
        new_menu.first.hover()

        strategy = page.locator(SELECTORS.pine_new_strategy)
        strategy.first.wait_for(state="visible", timeout=config.timeout_ms)
        strategy.first.click()
        page.wait_for_timeout(_KEYBOARD_SETTLE_MS)
    except Exception as exc:
        shot = capture_diagnostics(page, config.diagnostics_dir, "create_new_strategy")
        raise PineEditorError(
            f"Could not create new Strategy: {exc}",
            screenshot_path=shot,
        ) from exc


def _paste_into_editor(page: Page, text: str) -> None:
    """Write `text` to the clipboard and paste (Control/Meta+V)."""
    modifier = "Meta" if sys.platform == "darwin" else "Control"
    try:
        parsed = urlparse(page.url)
        if parsed.scheme and parsed.netloc:
            page.context.grant_permissions(
                ["clipboard-read", "clipboard-write"],
                origin=f"{parsed.scheme}://{parsed.netloc}",
            )
    except Exception:  # noqa: BLE001 — paste may still work without grant
        pass
    page.evaluate(
        """async (value) => {
            await navigator.clipboard.writeText(value);
        }""",
        text,
    )
    page.keyboard.press(f"{modifier}+V")


def _pine_editor_text_empty(page: Page) -> bool:
    return bool(
        page.evaluate(
            """() => {
                const el = document.querySelector("div.lines-content");
                return el != null && el.innerText === "";
            }"""
        )
    )


def _clear_pine_editor(page: Page) -> None:
    """Select-all + delete until ``div.lines-content`` innerText is empty."""
    modifier = "Meta" if sys.platform == "darwin" else "Control"
    for _ in range(100):
        if _pine_editor_text_empty(page):
            return
        page.keyboard.press(f"{modifier}+A")
        page.wait_for_timeout(_KEYBOARD_SETTLE_MS)
        page.keyboard.press("Backspace")
        page.wait_for_timeout(_KEYBOARD_SETTLE_MS)


def _paste_pine_lines(page: Page, source: str) -> None:
    """Paste `source` in chunks: Paste → End → Enter → Home → …"""
    lines = source.splitlines()
    if not lines:
        return
    chunks = [
        "\n".join(lines[i : i + _PASTE_CHUNK_LINES])
        for i in range(0, len(lines), _PASTE_CHUNK_LINES)
    ]
    for i, chunk in enumerate(chunks):
        _paste_into_editor(page, chunk)
        page.wait_for_timeout(_KEYBOARD_SETTLE_MS)
        if i >= len(chunks) - 1:
            break
        page.keyboard.press("End")
        page.wait_for_timeout(_KEYBOARD_SETTLE_MS)
        page.keyboard.press("Enter")
        page.wait_for_timeout(_KEYBOARD_SETTLE_MS)
        page.keyboard.press("Home")
        page.wait_for_timeout(_KEYBOARD_SETTLE_MS)


def apply_pine_script(page: Page, source: str, config: BacktestConfig) -> None:
    """
    Replace editor contents with `source` and add the strategy to the chart.

    Flow: open Pine Editor → create blank Strategy → click Monaco view-line →
    clear until lines-content is empty → paste in 100-line chunks
    (Paste → End → Enter → Home → …) → Add to chart.
    If Add is disabled (script already on chart unchanged), dirty the editor
    (click view-line → End → type ``//``) then click Add.
    If ``div.message[role=alert]`` appears, raises ``PineEditorError`` whose
    message is the alert's inner text.
    """
    try:
        open_pine_editor(page, config)
        create_new_strategy(page, config)

        view_line = page.locator(SELECTORS.pine_editor_view_line)
        view_line.first.wait_for(state="visible", timeout=config.timeout_ms)
        view_line.first.click()

        _clear_pine_editor(page)
        _paste_pine_lines(page, source)
        page.wait_for_timeout(500)

        add_btn = page.locator(SELECTORS.pine_add_to_chart)
        add_btn.first.wait_for(state="visible", timeout=config.timeout_ms)
        if add_btn.first.is_disabled():
            # Script unchanged from chart — dirty it so Add becomes enabled
            view_line.first.click()
            page.keyboard.press("End")
            page.keyboard.press("Enter")
            page.keyboard.type("//")
            page.wait_for_timeout(500)
        add_btn.first.click()

        # Surface Pine compile / runtime alert quickly (do not block 5s on success)
        alert = page.locator(SELECTORS.pine_editor_alert)
        try:
            alert.first.wait_for(state="visible", timeout=1_500)
            message = alert.first.inner_text().strip()
            shot = capture_diagnostics(page, config.diagnostics_dir, "pine_script_alert")
            raise PineEditorError(
                message or "Pine Editor reported an error",
                screenshot_path=shot,
            )
        except PlaywrightTimeoutError:
            pass

        try:
            # Confirm strategy landed: object-tree toggler appears on chart
            page.locator(SELECTORS.strategy_on_chart).first.wait_for(
                state="visible",
                timeout=min(config.timeout_ms, 20_000),
            )
        except PlaywrightTimeoutError:
            pass
    except PineEditorError:
        raise
    except Exception as exc:
        shot = capture_diagnostics(page, config.diagnostics_dir, "apply_pine_script")
        raise PineEditorError(
            f"Failed to apply Pine script: {exc}",
            screenshot_path=shot,
        ) from exc


def load_and_apply_pine(page: Page, config: BacktestConfig) -> str:
    source = read_pine_script(config.resolve_pine_script())
    apply_pine_script(page, source, config)
    return source
