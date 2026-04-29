# macau-dsec-scraper

澳門統計暨普查局（DSEC）時間序列數據庫 API 抓取器——**全自動，無需登入，無需手動操作瀏覽器**

## 成效

- **7,911** 個指標
- **154,050** 條時間序列
- 涵蓋 **1976–2025** 年
- 20 分類：人口、旅遊、GDP、博彩、貿易、就業、物價等

## 快速開始

```bash
# 安裝依賴（只需一次）
pip3 install playwright
playwright install chromium

# 一鍵自動抓取（自動獲取 cookies + 爬完全部數據）
python3 fetch_dsec_timeseries.py --auto-cookies
```

輸出：
- `dsec_timeseries.db`（SQLite）
- `cookies.json`（下次無需重複）

## 工作流程

```
1. 自動啟動 headless Chrome 訪問 DSEC
2. 自動抓取 session cookies（無需登入）
3. BFS 遍歷指標樹
4. 批量抓取所有指標的時間序列數據
```

## 腳本說明

| 腳本 | 說明 |
|------|------|
| `fetch_dsec_timeseries.py` | 主爬蟲（帶 `--auto-cookies` 一鍵模式） |
| `get_cookies.py` | 单独獲取 cookies |
| `key_indicators.json` | 5 個核心指標（20年歷史，clone 後直接用） |

## 查詢範例

```python
import sqlite3
conn = sqlite3.connect('dsec_timeseries.db')
c = conn.cursor()

# 找指標
c.execute("""
    SELECT indicator_id, indicator_path FROM indicators
    WHERE indicator_path LIKE '%本地生產總值%' LIMIT 5
""")
for row in c.fetchall():
    print(row)

# 看時間序列
c.execute("""
    SELECT reference_period, indicator_value
    FROM time_series
    WHERE indicator_id=1110 ORDER BY year DESC LIMIT 5
""")
for row in c.fetchall():
    print(row)
```

## API 端點（已逆向工程）

```bash
# 指標樹
curl "https://www.dsec.gov.mo/TimeSeriesApi/App/Indicatorv3" \
  -H "Cookie: $(cat cookies.json | python3 -c 'import sys,json; print("; ".join(f"{k}={v}" for k,v in json.load(sys.stdin).items()))')"

# 時間序列數據（POST）
curl -X POST "https://www.dsec.gov.mo/TimeSeriesApi/App/IndicatorValue/LatestSameEndPeriodv3" \
  -d "indicator_ids=1110&language=zh-MO&types=VAL&dataPeriods=Yearly&num=50"
```

詳見 [SKILL.md](SKILL.md)
