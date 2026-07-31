"""TradingView login with storage_state reuse to avoid frequent logins."""

from __future__ import annotations

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from tradingview_strategy_tools.browser import BrowserSession, capture_diagnostics, save_storage_state
from tradingview_strategy_tools.exceptions import AuthenticationError
from tradingview_strategy_tools.models import BacktestConfig, LoginCredentials
from tradingview_strategy_tools.selectors import SELECTORS


HOME_URL = "https://www.tradingview.com/"


def is_logged_in(page: Page, *, timeout_ms: int = 8_000) -> bool:
    """Heuristic: TradingView session cookie present after storage_state / login."""
    _ = timeout_ms
    cookies = page.context.cookies()
    names = {c.get("name", "") for c in cookies}
    return any(n == "sessionid" or n.startswith("sessionid") for n in names)


def ensure_authenticated(session: BrowserSession, config: BacktestConfig) -> bool:
    """
    Ensure the browser context has a valid TradingView session.

    Returns True if an existing storage_state was reused successfully
    (no password login performed). Returns False if a fresh login ran.
    Never loops login attempts — one attempt only.
    """
    page = session.page
    page.goto(HOME_URL, wait_until="domcontentloaded")

    # Persistent profile (and/or storage_state) may already have a valid session
    if is_logged_in(page, timeout_ms=min(config.timeout_ms, 12_000)):
        return True

    # Session missing / expired → single login
    _login_once(page, config.login, config)
    if not is_logged_in(page, timeout_ms=min(config.timeout_ms, 15_000)):
        shot = capture_diagnostics(page, config.diagnostics_dir, "login_failed")
        raise AuthenticationError(
            "Login did not establish a session. "
            "TradingView may require captcha / 2FA — complete it manually once "
            "and re-run so storage_state can be saved.",
            screenshot_path=shot,
        )

    save_storage_state(session.context, session.storage_state_path)
    return False


def _login_once(page: Page, credentials: LoginCredentials, config: BacktestConfig) -> None:
    """Perform a single automated email/password login attempt."""
    try:
        # 1. Open header user menu
        menu = page.locator(SELECTORS.user_menu_button)
        menu.first.wait_for(state="visible", timeout=config.timeout_ms)
        expanded = page.locator(SELECTORS.user_menu_expanded)
        try:
            if not expanded.first.is_visible(timeout=500):
                menu.first.click()
        except PlaywrightTimeoutError:
            menu.first.click()
        expanded.first.wait_for(state="visible", timeout=config.timeout_ms)

        # 2. Sign in from the menu
        page.locator(SELECTORS.sign_in_button).first.click()

        # 3. Email login path
        email_opt = page.locator(SELECTORS.email_login_option)
        email_opt.first.wait_for(state="visible", timeout=config.timeout_ms)
        email_opt.first.click()

        captcha = page.locator(SELECTORS.captcha_hint)
        try:
            if captcha.first.is_visible(timeout=1_000):
                shot = capture_diagnostics(page, config.diagnostics_dir, "captcha_detected")
                raise AuthenticationError(
                    "Captcha / extra verification detected. "
                    "Complete login manually in the opened browser, then re-run "
                    "so storage_state is reused without frequent logins.",
                    screenshot_path=shot,
                )
        except PlaywrightTimeoutError:
            pass

        # 4–5. Credentials
        username = page.locator(SELECTORS.username_input)
        password = page.locator(SELECTORS.password_input)
        username.first.wait_for(state="visible", timeout=config.timeout_ms)
        username.first.fill(credentials.username)
        password.first.fill(credentials.password)

        # 6. Submit
        page.locator(SELECTORS.submit_login).first.click()

        # Wait for login form to dismiss
        page.wait_for_timeout(2_000)
        username.first.wait_for(state="hidden", timeout=config.timeout_ms)
    except AuthenticationError:
        raise
    except Exception as exc:
        shot = capture_diagnostics(page, config.diagnostics_dir, "login_exception")
        raise AuthenticationError(
            f"Automated login failed: {exc}",
            screenshot_path=shot,
        ) from exc
