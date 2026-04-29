#!/usr/bin/env python3
"""
get_dsec_cookies.py
自動從 DSEC 網站取得 session cookies，無需手動操作瀏覽器
"""
from playwright.sync_api import sync_playwright
import json, sys

def get_dsec_cookies(cookies_file="cookies.json"):
    """使用 Playwright 啟動 headless Chrome，自動獲取 DSEC session cookies"""
    print("正在啟動瀏覽器...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            ignore_https_errors=True,
            java_script_enabled=True,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = ctx.new_page()
        
        print("訪問 DSEC 主頁...")
        page.goto("https://www.dsec.gov.mo/zh-MO/", timeout=20000)
        page.wait_for_timeout(2000)
        
        print("訪問 Time Series 頁面...")
        page.goto("https://www.dsec.gov.mo/ts/", timeout=20000)
        page.wait_for_timeout(3000)
        
        print("提取 cookies...")
        cookies = ctx.cookies()
        
        # 找出關鍵 cookies
        needed = ['cs', 's', '.AspNetCore.Mvc.CookieTempDataProvider']
        cookie_dict = {}
        found = []
        
        for c in cookies:
            name = c['name']
            value = c['value']
            cookie_dict[name] = value
            if name in needed:
                found.append(name)
        
        browser.close()
        
        # 測試 cookies 是否有效
        print("\n測試 cookies 是否有效...")
        import urllib.request
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
        req = urllib.request.Request("https://www.dsec.gov.mo/TimeSeriesApi/App/Indicatorv3")
        req.add_header("Cookie", cookie_header)
        req.add_header("User-Agent", "Mozilla/5.0")
        
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                count = len(data.get('Value', []) or [])
                print(f"✓ Cookies 有效！API 返回 {count} 個根指標")
        except Exception as e:
            print(f"✗ Cookies 無效: {e}")
            return None
        
        # 保存
        with open(cookies_file, 'w') as f:
            json.dump(cookie_dict, f, indent=2)
        print(f"✓ Cookies 已保存到 {cookies_file}")
        
        return cookie_dict

if __name__ == '__main__':
    cookies_file = sys.argv[1] if len(sys.argv) > 1 else "cookies.json"
    result = get_dsec_cookies(cookies_file)
    if result:
        print(f"\n成功！共取得 {len(result)} 個 cookies")
    else:
        print("\n失敗！可能需要檢查網絡或 DSEC 是否有新的驗證機制")
