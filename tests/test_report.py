"""Unit tests for strategy report CSV parsing and helpers."""

from __future__ import annotations

from tradingview_strategy_tools.report import build_key_factors, parse_trades_csv


_SAMPLE_CSV = """\
Trade number,Type,Date and time,Signal,Price USD,Size (qty),Size (value),Net PnL USD,Return %,Commission USD,Favorable excursion USD,Favorable excursion %,Adverse excursion USD,Adverse excursion %,Cumulative PnL USD,Cumulative PnL %,Duration (bars)
1,Exit long,2024-08-02,Close entry(s) order Long,219.15,1,182.35,36.8,20.18,0,54.88,30.10,-1.93,-1.06,36.8,0.37,61
1,Entry long,2024-05-06,Long,182.35,1,182.35,36.8,20.18,0,54.88,30.10,-1.93,-1.06,36.8,0.37,61
2,Exit long,2024-09-17,Close entry(s) order Long,215.75,1,227.79,-12.04,-5.29,0,5.13,2.25,-13.87,-6.09,24.76,0.25,17
"""


def test_parse_trades_csv_rows_and_types() -> None:
    trades = parse_trades_csv(_SAMPLE_CSV)
    assert len(trades) == 3
    assert trades[0]["Trade number"] == 1
    assert trades[0]["Type"] == "Exit long"
    assert trades[0]["Price USD"] == 219.15
    assert trades[0]["Net PnL USD"] == 36.8
    assert trades[0]["Duration (bars)"] == 61
    assert trades[2]["Net PnL USD"] == -12.04


def test_parse_trades_csv_empty() -> None:
    assert parse_trades_csv("") == []
    assert parse_trades_csv("   ") == []


def test_build_key_factors_from_overview_cells() -> None:
    key_factors = build_key_factors(
        [
            {
                "title": "Total PnL",
                "value": "+32.94",
                "currency": "USD",
                "change": "+0.33%",
            },
            {
                "title": "Max drawdown",
                "value": "22.37",
                "currency": "USD",
                "change": "0.22%",
            },
            {
                "title": "Profitable trades",
                "value": "33.33%",
                "currency": "",
                "change": "1/3",
            },
            {
                "title": "Profit factor",
                "value": "1.89",
                "currency": "",
                "change": "",
            },
        ]
    )
    assert key_factors == {
        "total_pnl": {"value": "+32.94 USD", "percentage": "+0.33%"},
        "max_drawdown": {"value": "22.37 USD", "percentage": "0.22%"},
        "profitable_trades": {"value": "1/3", "percentage": "33.33%"},
        "profit_factor": 1.89,
    }


def test_build_key_factors_empty() -> None:
    assert build_key_factors([]) is None
    assert build_key_factors([{"title": "", "value": "1"}]) is None
