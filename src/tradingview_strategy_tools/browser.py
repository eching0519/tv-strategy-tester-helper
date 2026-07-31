"""Playwright browser / context lifecycle helpers."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from tradingview_strategy_tools.models import BacktestConfig


@dataclass
class BrowserSession:
    playwright: Playwright
    browser: Browser | None
    context: BrowserContext
    page: Page
    storage_state_path: Path
    used_existing_state: bool


def _persistent_context_kwargs(headless: bool) -> dict:
    """
    Build kwargs for launch_persistent_context.

    TradingView's Pine Editor hangs forever in ephemeral/incognito contexts
    (browser.new_context). A persistent user-data profile is required.

    Note: launch_persistent_context does not accept storage_state; cookies from
    an existing storage_state file are applied after launch via add_cookies.
    """
    return {
        "headless": headless,
        "viewport": {"width": 1440, "height": 900},
        "locale": "en-US",
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "args": [
            "--disable-blink-features=AutomationControlled",
        ],
    }


def apply_storage_state_cookies(context: BrowserContext, path: Path) -> bool:
    """Import cookies from a Playwright storage_state JSON file. Returns True if applied."""
    path = path.expanduser()
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    cookies = data.get("cookies") or []
    if not cookies:
        return False
    context.add_cookies(cookies)
    return True


@contextmanager
def browser_session(config: BacktestConfig) -> Iterator[BrowserSession]:
    """Yield a non-incognito Chromium context with a persistent user-data dir."""
    storage_path = config.storage_state_path.expanduser()
    user_data_dir = config.user_data_dir.expanduser()
    user_data_dir.mkdir(parents=True, exist_ok=True)
    used_existing = storage_path.is_file()

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            **_persistent_context_kwargs(headless=config.headless),
        )
        context.set_default_timeout(config.timeout_ms)
        if used_existing:
            apply_storage_state_cookies(context, storage_path)
        page = context.pages[0] if context.pages else context.new_page()
        session = BrowserSession(
            playwright=playwright,
            browser=context.browser,
            context=context,
            page=page,
            storage_state_path=storage_path,
            used_existing_state=used_existing,
        )
        try:
            yield session
        finally:
            context.close()


def save_storage_state(context: BrowserContext, path: Path) -> None:
    """Atomically persist cookies/localStorage for reuse."""
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    context.storage_state(path=str(tmp))
    tmp.replace(path)


def capture_diagnostics(page: Page, diagnostics_dir: Path, label: str) -> Path | None:
    """Save a screenshot for failed steps; return path or None on failure."""
    try:
        diagnostics_dir = diagnostics_dir.expanduser()
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:64]
        path = diagnostics_dir / f"{stamp}_{safe_label}.png"
        page.screenshot(path=str(path), full_page=True)
        return path
    except Exception:  # noqa: BLE001 — diagnostics must not mask original error
        return None
