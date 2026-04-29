#!/usr/bin/env python3
"""
DSEC Time Series Database Scraper
自動抓取澳門統計暨普查局時間序列數據庫完整歷史數據
"""
import urllib.request, urllib.parse, json, sqlite3, time, os
from datetime import datetime

"""
DSEC Time Series Database Scraper
自動抓取澳門統計暨普查局時間序列數據庫完整歷史數據

用法:
  1. 首次運行自動獲取 cookies（需安裝 playwright）:
       python3 fetch_dsec_timeseries.py --auto-cookies
  2. 或先单独获取 cookies:
       python3 get_cookies.py
       python3 fetch_dsec_timeseries.py
"""

COOKIES = []
COOKIE_HEADER = ""

def load_cookies(path="cookies.json"):
    global COOKIES, COOKIE_HEADER
    if os.path.exists(path):
        with open(path) as f:
            cookie_dict = json.load(f)
        COOKIES = list(cookie_dict.items())
        COOKIE_HEADER = "; ".join(f"{k}={v}" for k, v in COOKIES)
        return True
    return False

def auto_get_cookies():
    """使用 Playwright 自動從瀏覽器獲取 cookies"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("需要先安裝 playwright: pip3 install playwright && playwright install chromium")
        return False
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        
        page.goto("https://www.dsec.gov.mo/zh-MO/", timeout=20000)
        page.wait_for_timeout(2000)
        page.goto("https://www.dsec.gov.mo/ts/", timeout=20000)
        page.wait_for_timeout(3000)
        
        cookies = ctx.cookies()
        ctx.cookies()
        
        cookie_dict = {c['name']: c['value'] for c in cookies}
        
        # 測試是否有效
        import urllib.request
        hdr = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
        req = urllib.request.Request("https://www.dsec.gov.mo/TimeSeriesApi/App/Indicatorv3")
        req.add_header("Cookie", hdr)
        req.add_header("User-Agent", "Mozilla/5.0")
        
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                if data.get('Value'):
                    with open('cookies.json', 'w') as f:
                        json.dump(cookie_dict, f)
                    print(f"✓ cookies.json 已生成，共 {len(cookie_dict)} 個 cookies")
                    load_cookies()
                    return True
        except Exception as e:
            print(f"✗ cookies 無效: {e}")
        
        browser.close()
        return False

def ensure_cookies():
    global COOKIE_HEADER
    if not COOKIE_HEADER:
        if '--auto-cookies' in sys.argv:
            if not auto_get_cookies():
                print("自動獲取 cookies 失敗，請先運行: python3 get_cookies.py")
                sys.exit(1)
        elif not load_cookies():
            print("找不到 cookies.json，請先運行: python3 get_cookies.py")
            sys.exit(1)

import sys
ensure_cookies()
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dsec_timeseries.db")

def api_get(url):
    req = urllib.request.Request(url)
    req.add_header("Cookie", COOKIE_HEADER)
    req.add_header("User-Agent", "Mozilla/5.0")
    req.add_header("Referer", "https://www.dsec.gov.mo/ts/")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode('utf-8'))

def api_post(url, params):
    req = urllib.request.Request(url, data=params.encode(), method='POST')
    req.add_header("Cookie", COOKIE_HEADER)
    req.add_header("User-Agent", "Mozilla/5.0")
    req.add_header("Referer", "https://www.dsec.gov.mo/ts/")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode('utf-8'))

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS indicators (
        indicator_id INTEGER PRIMARY KEY,
        display_id REAL,
        description TEXT,
        description_sc TEXT,
        description_pt TEXT,
        description_en TEXT,
        parent_id REAL,
        is_leaf_node INTEGER,
        yearly_available INTEGER,
        quarterly_available INTEGER,
        monthly_available INTEGER,
        val_available INTEGER,
        min_year TEXT,
        max_year TEXT,
        unit_label TEXT,
        indicator_path TEXT,
        fetched_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS time_series (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        indicator_id INTEGER,
        reference_period TEXT,
        year INTEGER,
        indicator_value REAL,
        unit_label TEXT,
        last_update TEXT,
        type TEXT,
        fetched_at TEXT
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_ts_indicator ON time_series(indicator_id)')
    conn.commit()
    return conn

def save_indicator(conn, ind):
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO indicators VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (ind['IndicatorID'], ind.get('DisplayID'), ind.get('Description'),
         ind.get('DescriptionSimplifiedChinese'), ind.get('DescriptionPort'), ind.get('DescriptionEngl'),
         ind.get('Parent'),
         1 if ind.get('IsLeafNode') in (True, 'True') else 0,
         1 if ind.get('YearlyAvailable') == 'True' else 0,
         1 if ind.get('QuarterlyAvailable') == 'True' else 0,
         1 if ind.get('MonthlyAvailable') == 'True' else 0,
         1 if ind.get('VALAvailable') == 'True' else 0,
         ind.get('minYear'), ind.get('maxYear'), ind.get('UnitLabel'),
         ind.get('IndicatorPath_zhMO'), datetime.now().isoformat()))
    conn.commit()

def save_time_series(conn, indicator_id, records):
    c = conn.cursor()
    now = datetime.now().isoformat()
    for rec in records:
        c.execute('''INSERT INTO time_series 
            (indicator_id, reference_period, year, indicator_value, unit_label, last_update, type, fetched_at)
            VALUES (?,?,?,?,?,?,?,?)''',
            (indicator_id, rec.get('ReferencePeriod'), rec.get('Year'),
             rec.get('IndicatorValue'), rec.get('UnitLabel'),
             rec.get('LastUpdateDate'), rec.get('type'), now))
    conn.commit()

def get_indicator_children(indicator_id):
    try:
        data = api_get(f"https://www.dsec.gov.mo/TimeSeriesApi/App/Indicatorv3/{int(indicator_id)}")
        return data.get('Value', []) or []
    except Exception as e:
        return []

def fetch_time_series_data(indicator_id, ind_type='VAL', data_period='Yearly', num=50):
    params = f"indicator_ids={indicator_id}&language=zh-MO&types={ind_type}&dataPeriods={data_period}&num={num}"
    try:
        data = api_post("https://www.dsec.gov.mo/TimeSeriesApi/App/IndicatorValue/LatestSameEndPeriodv3", params)
        if data.get('Value'):
            return data['Value'][0].get('dsecIndicatorData', [])
    except:
        pass
    return []

def main():
    print(f"[{datetime.now()}] DSEC Time Series Scraper starting...")
    conn = init_db()
    
    print("Step 1: Fetching root indicator tree...")
    root_data = api_get("https://www.dsec.gov.mo/TimeSeriesApi/App/Indicatorv3")
    root_items = root_data.get('Value', []) or []
    print(f"  Root categories: {len(root_items)}")
    
    print("Step 2: Exploring indicator tree...")
    visited_paths = set()
    all_leaves = []
    
    def process_items(items):
        for item in items:
            iid = item['IndicatorID']
            if iid in visited_paths:
                continue
            visited_paths.add(iid)
            
            if item.get('IsLeafNode') in (True, 'True'):
                save_indicator(conn, item)
                all_leaves.append(item)
                print(f"  [LEAF] {item.get('IndicatorPath_zhMO', item.get('Description',''))[:70]}")
            else:
                children = get_indicator_children(iid)
                if children:
                    process_items(children)
                else:
                    item['IsLeafNode'] = 'True'
                    save_indicator(conn, item)
                    all_leaves.append(item)
    
    process_items(root_items)
    print(f"\nTotal leaf indicators: {len(all_leaves)}")
    
    print("Step 3: Fetching time series data...")
    period_priority = ['Yearly', 'Quarterly', 'Monthly', 'ThreeConsecutiveMonths',
                       'SchoolTerm', 'TwoConsecutiveYears', 'ThreeConsecutiveYears', 'FourConsecutiveYears']
    
    success = 0
    fail = 0
    
    for ind in all_leaves:
        iid = ind['IndicatorID']
        data_period = None
        for period in period_priority:
            if ind.get(f'{period}Available') == 'True':
                data_period = period
                break
        if not data_period:
            data_period = 'Yearly'
        
        ind_type = ind.get('Type') or 'VAL'
        records = fetch_time_series_data(iid, ind_type, data_period, num=50)
        
        if records:
            save_time_series(conn, iid, records)
            success += 1
            if success % 20 == 0:
                print(f"  Progress: {success} OK, {fail} failed")
        else:
            fail += 1
        
        time.sleep(0.25)
    
    print(f"\nDone! {success} indicators with data, {fail} without")
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM indicators'); print(f"Total indicators: {c.fetchone()[0]}")
    c.execute('SELECT COUNT(*) FROM time_series'); print(f"Total records: {c.fetchone()[0]}")
    conn.close()
    print(f"[{datetime.now()}] Finished.")

if __name__ == '__main__':
    main()
