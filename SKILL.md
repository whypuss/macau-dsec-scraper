---
name: macau-dsec-scraper
description: 澳門統計暨普查局（DSEC）時間序列數據庫 API 抓取器——登陸無需登入的 DSEC Time Series Portal，批量抓取 7,911 個指標、15 萬條歷史數據
category: data-science
---

# macau-dsec-scraper

澳門統計暨普查局（DSEC）時間序列數據庫（Time Series Database）自動抓取工具。

## 成效

- **7,911** 個指標
- **154,050** 條時間序列記錄
- 涵蓋 **1976–2025** 年歷史數據
- 20 個主要分類：人口、旅遊、GDP、博彩、貿易、就業等

## 登陸方式

### 1. 找到 API 端點

使用 **Chrome DevTools** 攔截 DSEC Time Series 網頁的網絡請求：

1. 打開 `https://www.dsec.gov.mo/ts/`
2. 按 F12 開 DevTools → **Network** 面板
3. 點任意指標（觸發 API）
4. 找到 `TimeSeriesApi` 路徑的請求

關鍵端點（逆向工程自 AngularJS SPA）：

| 操作 | 方法 | URL |
|------|------|-----|
| 指標樹（根） | `GET` | `https://www.dsec.gov.mo/TimeSeriesApi/App/Indicatorv3` |
| 子節點 | `GET` | `https://www.dsec.gov.mo/TimeSeriesApi/App/Indicatorv3/{indicatorID}` |
| **時間序列數據** | `POST` | `https://www.dsec.gov.mo/TimeSeriesApi/App/IndicatorValue/LatestSameEndPeriodv3` |

### 2. 獲取 Cookies

從 DevTools **Application** → **Cookies** → `https://www.dsec.gov.mo` 複製以下 cookie：

```
cs=...
s=...
.AspNetCore.Mvc.CookieTempDataProvider=...
```

這些是 httpOnly session cookie，必須從瀏覽器取得。

### 3. 呼叫時間序列數據 API

```bash
curl -X POST "https://www.dsec.gov.mo/TimeSeriesApi/App/IndicatorValue/LatestSameEndPeriodv3" \
  -H "Cookie: cs=...; s=...; .AspNetCore.Mvc.CookieTempDataProvider=..." \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "indicator_ids=15001&language=zh-MO&types=VAL&dataPeriods=Yearly&num=50"
```

**參數說明：**

| 參數 | 說明 | 範例 |
|------|------|------|
| `indicator_ids` | 指標 ID（從 Indicatorv3 取得） | `15001`, `55139` |
| `language` | 語言 | `zh-MO` / `en` |
| `types` | **值類型**，不是週期！ | `VAL`（標準數值） |
| `dataPeriods` | 時間週期 | `Yearly` / `Quarterly` / `Monthly` |
| `num` | 抓多少筆 | `50` |

**`types=VAL` 是關鍵：** 不是 "Yearly"，是 `VAL`（標準數值）。`Yearly` 是傳入 `dataPeriods` 的參數。

### 4. 自動抓取腳本

```python
# scripts/fetch_dsec_timeseries.py
# 全自動：登陸 → 遍歷指標樹 → 批量抓取 → 存入 SQLite
python3 fetch_dsec_timeseries.py
```

輸出：
- `dsec_timeseries.db`（SQLite）
- 日誌：`fetch_log.txt`

## 常見陷阱

### AngularJS digest cycle 不觸發

Headless Chrome/Playwright 環境下，點擊 UI 不會發 API 請求（Angular digest loop 不運行）。

**解決：** 不要依賴 UI 操作，直接從瀏覽器 DevTools 複製 cookies，然後用 Python `urllib` 直call API。

### `types` vs `dataPeriods` 混淆

`types=VAL` 是**值類型**（VAL = 標準數值，還有 SPV/PPV/POT/PPD 等）。
`dataPeriods=Yearly` 才是**時間週期**（年度/季度/月度）。

### `indicator_path` vs `description`

DSEC API 返回的 `description` 通常很短（如 "男"、"女"），真正的指標名稱在 `indicator_path` 欄位：

```
description: "女"
indicator_path: "人口 -- 總人口 -- 按性別 -- 女"
```

搜尋要用 `indicator_path LIKE '%總人口%'`，不要用 `description`。

### `IsLeafNode` 不靠譜

幾乎所有節點的 `IsLeafNode` 都是 `True`。判斷父子關係要看 `indicator_path` 的 `--` 分隔層級，或根據 `parent_id` 欄位。

## 數據驗證（2025）

| 指標 | 數值 | 備註 |
|------|------|------|
| 人均GDP（當年價格） | 607,263 澳門元 | |
| 人均GDP（美元） | 75,617 USD | |
| 總人口 | 689,000 人 | 男 318 + 女 371（千人） |
| 外地僱員（新簽發） | 56,472 人 | |
| 博彩毛收入 | 13,866 百萬（MOP） | 幸運博彩機 |

## 文件結構

```
macau-dsec-scraper/
├── SKILL.md              # 本文件
├── scripts/
│   └── fetch_dsec_timeseries.py   # 完整抓取腳本
└── README.md
```

## 依賴

```bash
pip3 install # 標準庫：urllib, sqlite3, json, time
```
