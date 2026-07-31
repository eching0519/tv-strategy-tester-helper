"""
Centralized TradingView UI selectors.

TradingView DOM changes frequently — update locators here without touching
orchestration logic. Prefer role/text/data-name attributes when available.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Selectors:
    # --- Auth / session ---
    # Guest header menu (open → Sign in). Logged-in avatar also uses this class.
    user_menu_button: str = "button.tv-header__user-menu-button"
    user_menu_expanded: str = 'button.tv-header__user-menu-button[aria-expanded="true"]'
    sign_in_button: str = 'button[data-name="header-user-menu-sign-in"]'
    email_login_option: str = 'button[name="Email"]'
    username_input: str = "#id_username"
    password_input: str = "#id_password"
    submit_login: str = "button.submitButton-gTIIv2RF"
    # Extra verification / captcha hints
    captcha_hint: str = '[class*="captcha" i], iframe[src*="captcha" i], [data-name="captcha"]'

    # --- Chart / timeframe ---
    chart_container: str = "div.chart-container"
    layouts_button: str = "#header-toolbar-layouts"
    # First layout option (single chart) in the layouts popover
    layout_single_button: str = "div.rowButtons-RLufNh8B"
    timeframe_button: str = 'button[aria-label="Change interval"]'
    timeframe_input: str = "input[data-qa-id=ui-lib-Input-input]"
    # Object tree / legend: expand when collapsed, then delete sources
    object_tree_closed: str = "div.closed-quatTGAC"
    object_tree_toggler: str = "button.toggler-quatTGAC"
    # Hover target that reveals the delete button on each legend source
    legend_titles: str = 'div.sources-quatTGAC div[data-qa-id="legend-titles"]'
    legend_delete_action: str = 'button[data-qa-id="legend-delete-action"]'

    # --- Pine Editor ---
    # Open via Products menu → Pine Editor menuitem
    products_button: str = 'button[data-qa-id="products-button"]'
    pine_editor_menuitem: str = (
        'div[data-qa-id="popup-menu-container"] '
        'div[data-role="menuitem"]:has-text("Pine Editor")'
    )
    pine_editor_title: str = "div.titleSlot-ITRSDHoo"
    pine_editor_open: str = "div.titleSlot-ITRSDHoo"
    # Monaco editor line (click to focus before select-all / paste)
    pine_editor_view_line: str = "div.monaco-scrollable-element div.view-line"
    pine_add_to_chart: str = 'button[data-qa-id="add-script-to-chart"]'
    # Compile / runtime error banner in Pine Editor
    pine_editor_alert: str = 'div.message[role="alert"]'
    # Present when a strategy / indicator object tree is on the chart
    strategy_on_chart: str = "button.toggler-quatTGAC"

    # --- Strategy Tester ---
    strategy_tester_tab: str = (
        'button[data-name="backtesting"], '
        'button[aria-label*="Strategy Tester" i], '
        'button:has-text("Strategy Tester"), '
        'button:has-text("策略測試器")'
    )
    # Present when Strategy Tester panel is open
    date_range_menu: str = 'button[data-qa-id="date-range-menu"]'
    date_range_preset_button: str = "div.button-XNUivTou"
    date_range_input: str = 'input[data-qa-id="ui-lib-Input-input"]'
    date_range_submit: str = 'button[name="submit"]'

    # --- Strategy Report ---
    # Shown when the strategy made no trades in the selected period
    strategy_report_empty_title: str = "strong.title-D6_nhOMF"
    strategy_initial_capital: str = 'button[data-qa-id="initial-capital"]'
    strategy_overview_tab: str = 'button[data-name="light-tab-0"]'
    strategy_key_facts: str = 'div[data-qa-id="strategy-key-facts"]'
    strategy_list_of_trades_tab: str = 'button[data-name="light-tab-1"]'
    strategy_download_csv: str = "button.downloadButton-PgtNiNYX"


SELECTORS = Selectors()
