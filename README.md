# macau-dsec-scraper

澳門統計暨普查局（DSEC）時間序列數據庫 API 抓取器

## 成效

- **7,911** 個指標
- **154,050** 條時間序列
- 涵蓋 **1976–2025** 年
- 20 分類：人口、旅遊、GDP、博彩、貿易、就業、物價等

## 快速開始

### 1. 取得 Cookies

在 Chrome 打開 `https://www.dsec.gov.mo/ts/`，按 F12 → Application → Cookies，複製 `cs`、`s`、`.AspNetCore.Mvc.CookieTempDataProvider`。

### 2. 抓取數據

```bash
python3 scripts/fetch_dsec_timeseries.py
```

輸出：`scripts/dsec_timeseries.db`

### 3. 查詢範例

```python
import sqlite3
conn = sqlite3.connect('scripts/dsec_timeseries.db')
c = conn.cursor()

# 找指標
c.execute("SELECT indicator_id, indicator_path FROM indicators WHERE indicator_path LIKE '%本地生產總值%' LIMIT 5")
for row in c.fetchall():
    print(row)

# 看時間序列
c.execute("SELECT reference_period, indicator_value FROM time_series WHERE indicator_id=1110 ORDER BY year DESC LIMIT 5")
for row in c.fetchall():
    print(row)
```

## API 端點（已逆向工程）

```bash
# 指標樹
curl "https://www.dsec.gov.mo/TimeSeriesApi/App/Indicatorv3" \
  -H "Cookie: cs=...; s=...; .AspNetCore.Mvc.CookieTempDataProvider=..."

# 時間序列數據（POST）
curl -X POST "https://www.dsec.gov.mo/TimeSeriesApi/App/IndicatorValue/LatestSameEndPeriodv3" \
  -H "Cookie: cs=...; s=...; .AspNetCore.Mvc.CookieTempDataProvider=..." \
  -d "indicator_ids=1110&language=zh-MO&types=VAL&dataPeriods=Yearly&num=50"
```

詳見 [SKILL.md](SKILL.md)
