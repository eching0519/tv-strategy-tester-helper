# TradingView Strategy Tools

Playwright 自動化工具：登入 TradingView（並快取 session）、載入 Pine Script、設定圖表與 **Deep Backtesting** 日期範圍，最後輸出 Strategy Report 的 key factors（結構化 JSON）與 trades（CSV 解析為 JSON）。

## 功能

| 輸入 | 來源 |
|------|------|
| 帳密 / session / headless | `credentials.json`（靜態） |
| Pine Script 路徑 | 參數 `--pine` |
| Symbol | 參數 `--symbol` |
| Timeframe | 參數 `--timeframe` |
| 回測日期 | 參數 `--start` / `--end` |

| 輸出 | 說明 |
|------|------|
| `message` | `"success"`；無成交時為 `"success, but ..."` |
| `key_factors` | Overview key facts 結構化物件；無成交時為 `null` |
| `trades` | List of Trades CSV 解析後的 JSON 陣列；無成交時為 `[]` |

## 安裝

```bash
cd tradingview-strategy-tools
python -m pip install -e ".[dev]"
playwright install chromium
```

## 設定

複製範例並填入真實帳密（`credentials.json` 已在 `.gitignore`）：

```bash
copy credentials.example.json credentials.json
```

```json
{
  "login": {
    "username": "your_email@example.com",
    "password": "your_password"
  },
  "storage_state_path": "data/tradingview_login.json",
  "user_data_dir": "data/browser_profile",
  "headless": false,
  "timeout_ms": 60000
}
```

## 使用方式

### CLI

```bash
tradingview-backtest credentials.json ^
  --pine examples/sample_strategy.pine ^
  --symbol NASDAQ:AAPL ^
  --timeframe 1D ^
  --start 2024-01-01 ^
  --end 2024-12-31
```

Stdout 僅輸出結果 JSON（不含帳密）：

```json
{
  "message": "success",
  "key_factors": {
    "total_pnl": { "value": "+32.94 USD", "percentage": "+0.33%" },
    "max_drawdown": { "value": "22.37 USD", "percentage": "0.22%" },
    "profitable_trades": { "value": "1/3", "percentage": "33.33%" },
    "profit_factor": 1.89
  },
  "trades": [
    {
      "Trade number": 1,
      "Type": "Entry long",
      "Date and time": "2024-05-06",
      "Price USD": 182.35
    }
  ],
  "symbol": "NASDAQ:AAPL",
  "timeframe": "1D",
  "backtest": {
    "start": "2024-01-01",
    "end": "2024-12-31",
    "initial_capital": "10,000 USD"
  },
  "reused_session": true
}
```

### Python 函式

```python
from tradingview_strategy_tools import CredentialsConfig, run_backtest

credentials = CredentialsConfig.model_validate({...})
result = run_backtest(
    credentials=credentials,
    pine_script_path="examples/sample_strategy.pine",
    symbol="NASDAQ:AAPL",
    timeframe="1D",
    start="2024-01-01",
    end="2024-12-31",
)
print(result.message, result.key_factors, result.trades)
```

## Session 快取（避免頻繁登入）

為降低被 TradingView 封鎖的風險：

1. 首次執行會自動帳密登入一次。
2. 成功後將 cookies / storage 寫入 `storage_state_path`（預設 `data/tradingview_login.json`）。
3. 瀏覽器使用 **persistent profile**（`user_data_dir`，預設 `data/browser_profile`），避免 Playwright 的 ephemeral/incognito context —— TradingView Pine Editor 在無痕模式下會一直載入。
4. 只有當既有 session **無效** 時才會再登入一次（不會迴圈重試）。
5. 若出現 captcha / 2FA，請在 headed 瀏覽器手動完成後重跑，讓 session 被保存。

## 調整 TradingView UI 互動

TradingView DOM 常變。所有 locator 集中在：

- [`src/tradingview_strategy_tools/selectors.py`](src/tradingview_strategy_tools/selectors.py)

流程模組（可各自微調）：

| 模組 | 職責 |
|------|------|
| `auth.py` | 登入 / session 驗證 |
| `chart.py` | 開圖、symbol URL、timeframe |
| `pine.py` | 讀檔、Pine Editor、Add to chart |
| `report.py` | Strategy Tester、Deep Backtesting、key factors outerHTML、trades CSV→JSON |
| `runner.py` | 串接主流程 |

失敗時會嘗試在 `screenshots/`（或 `diagnostics_dir`）存截圖。

## 注意事項

- **Deep Backtesting** 通常需要付費方案；若 UI 找不到開關，請檢查帳戶權限或更新 `selectors.py`。
- 預設 `headless: false`，方便你調整互動與處理驗證。
- 請勿把真實帳密、`tradingview_login.json` 提交到 git。

## 測試

```bash
pytest
```

單元測試使用 mock，不會連線 TradingView，也不會觸發登入。

## 授權

依專案需要自行補充。
