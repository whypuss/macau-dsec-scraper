#!/usr/bin/env python3
"""
macau_llm_analyzer.py

澳門宏觀經濟維基 — 智能分析引擎

功能：
  1. 純 Python 統計分析（趨勢、異常、預測）
  2. 準備好 LLM 插槽，設定 OPENROUTER_API_KEY / MINIMAX_API_KEY / HF_TOKEN 後自動啟用

用法:
  python3 macau_llm_analyzer.py analyze GDP
  python3 macau_llm_analyzer.py trend 失業率
  python3 macau_llm_analyzer.py compare GDP 博彩
  python3 macau_llm_analyzer.py llm "澳門2024年經濟表現如何？"
  python3 macau_llm_analyzer.py update-wiki
"""

import sqlite3
import json
import os
import sys
import re
from datetime import datetime
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────
DB_PATH = os.path.expanduser("~/projects/history-knowledge-base-obsidian/dsec-time-series/dsec_timeseries.db")
WIKI_DIR  = os.path.expanduser("~/projects/history-knowledge-base-obsidian/澳門知識庫/DSEC 時間序列")

# ── LLM Config ────────────────────────────────────────────────────
def get_llm_client():
    """Return LLM client based on available API keys in environment."""
    # Check OpenRouter first
    key = os.environ.get("OPENROUTER_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    if key:
        return OpenRouterClient(key)

    # Check MiniMax
    for env_var in ["MINIMAX_API_KEY", "MINIMAX_CN_API_KEY"]:
        key = os.environ.get(env_var, "")
        if key and "***" not in key and len(key) > 10:
            return MiniMaxClient(key)

    # Check HF_TOKEN (for HF Inference API Pro accounts)
    hf_token = os.environ.get("HF_TOKEN", "")
    if hf_token and "***" not in hf_token:
        return HuggingFaceClient(hf_token)

    return None  # No LLM available


class OpenRouterClient:
    """OpenRouter API client."""
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
    MODELS = ["anthropic/claude-sonnet-4-5", "google/gemini-2.0-flash-exp", "meta-llama/llama-3.3-70b-instruct"]

    def __init__(self, api_key: str):
        self.api_key = api_key

    def complete(self, prompt: str, model: str = None) -> str:
        import urllib.request
        model = model or self.MODELS[0]
        req = urllib.request.Request(
            self.BASE_URL,
            data=json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 1024,
            }).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://macau-dsec-wiki",
            }
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]


class MiniMaxClient:
    """MiniMax API client."""
    BASE_URL = "https://api.minimaxi.com/v1/chat/completions"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def complete(self, prompt: str, model: str = "MiniMax-Text-01") -> str:
        import urllib.request
        req = urllib.request.Request(
            self.BASE_URL,
            data=json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 1024,
            }).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]


class HuggingFaceClient:
    """HuggingFace Inference API client (Pro account required)."""
    BASE_URL = "https://api-inference.huggingface.co/v1/chat/models/{model}"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def complete(self, prompt: str, model: str = "meta-llama/Llama-3.3-70B-Instruct") -> str:
        import urllib.request
        url = self.BASE_URL.format(model=model.replace("/", "-"))
        req = urllib.request.Request(
            f"https://api-inference.huggingface.co/models/{model}",
            data=json.dumps({"inputs": prompt, "parameters": {"temperature": 0.3, "max_new_tokens": 512}}).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            if isinstance(data, list):
                return data[0].get("generated_text", "")
            return data.get("generated_text", str(data))


# ── LLM Complete ──────────────────────────────────────────────────
def llm_complete(prompt: str) -> Optional[str]:
    client = get_llm_client()
    if client is None:
        return None
    try:
        return client.complete(prompt)
    except Exception as e:
        print(f"[LLM Warning: {e}]", file=sys.stderr)
        return None


# ── DB helpers ────────────────────────────────────────────────────
def get_db():
    return sqlite3.connect(DB_PATH)

def find_indicators(keyword: str, limit: int = 5):
    conn = get_db()
    c = conn.cursor()
    pattern = f"%{keyword}%"
    c.execute("""SELECT indicator_id, description, indicator_path, unit_label, min_year, max_year
        FROM indicators WHERE is_leaf_node=1
        AND (indicator_path LIKE ? OR description LIKE ?)
        ORDER BY
            CASE WHEN description = '總體' THEN 0 ELSE 1 END,
            indicator_path
        LIMIT ?""", (pattern, pattern, limit))
    rows = c.fetchall()
    conn.close()
    return rows

def get_series(indicator_id: int, years: int = 30):
    """Get time series data ordered by year ascending (oldest first)."""
    conn = get_db()
    c = conn.cursor()
    # Always get ALL rows, then slice - LIMIT with ASC gives wrong results
    c.execute("""SELECT reference_period, indicator_value, unit_label, year
        FROM time_series WHERE indicator_id=? AND indicator_value IS NOT NULL
        ORDER BY year ASC""", (str(indicator_id),))
    rows = c.fetchall()
    conn.close()
    # Return last N years (most recent)
    return [(r[0], r[1], r[2], r[3]) for r in rows[-years:]]


# ── Statistical analysis ───────────────────────────────────────────
def compute_stats(values):
    """Compute basic statistics for a series."""
    import statistics
    if len(values) < 2:
        return {}
    return {
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0,
        "min": min(values),
        "max": max(values),
        "latest": values[-1],
        "earliest": values[0],
        "pct_change_total": (values[-1] - values[0]) / values[0] * 100 if values[0] != 0 else 0,
        "pct_change_1y": (values[-1] - values[-2]) / values[-2] * 100 if len(values) > 1 and values[-2] != 0 else 0,
    }

def detect_anomalies(values, years, threshold_stdev=1.5):
    """Detect anomalies (> threshold_stdev from rolling mean)."""
    import statistics
    if len(values) < 3:
        return []
    anomalies = []
    mean = statistics.mean(values)
    stdev = statistics.stdev(values)
    for i, (yr, val) in enumerate(zip(years, values)):
        if abs(val - mean) > threshold_stdev * stdev:
            anomalies.append((yr, val, (val - mean) / stdev if stdev else 0))
    return anomalies

def detect_turning_points(values, years):
    """Detect local peaks and troughs."""
    if len(values) < 3:
        return []
    turning = []
    for i in range(1, len(values) - 1):
        if values[i] > values[i-1] and values[i] > values[i+1]:
            turning.append((years[i], values[i], "peak"))
        elif values[i] < values[i-1] and values[i] < values[i+1]:
            turning.append((years[i], values[i], "trough"))
    return turning

def linear_trend(years, values):
    """Simple linear regression."""
    if len(values) < 3:
        return None
    n = len(values)
    x_mean = sum(years) / n
    y_mean = sum(values) / n
    num = sum((years[i] - x_mean) * (values[i] - y_mean) for i in range(n))
    den = sum((years[i] - x_mean) ** 2 for i in range(n))
    if den == 0:
        return None
    slope = num / den
    intercept = y_mean - slope * x_mean
    return {"slope": slope, "intercept": intercept, "direction": "up" if slope > 0 else "down"}


# ── Formatters ─────────────────────────────────────────────────────
def format_series_md(rows, label="數值", include_changes=True):
    """Format time series as markdown table."""
    if not rows:
        return "(無數據)"
    lines = [f"| 年份 | {label} | 同比變動 |", "|------|------|--------|"]
    prev = None
    for period, val, unit, year in rows:
        unit_str = f" {unit}" if unit else ""
        change = ""
        if prev is not None and prev != 0:
            pct = (val - prev) / prev * 100
            change = f"{pct:+.1f}%"
        lines.append(f"| {year} | {val:,.2f}{unit_str} | {change} |")
        prev = val
    return "\n".join(lines)


# ── Core analysis commands ──────────────────────────────────────────

def cmd_analyze(keyword: str):
    """Full statistical analysis for an indicator."""
    print(f"\n=== 分析：{keyword} ===\n")
    rows = find_indicators(keyword)
    if not rows:
        print(f"未找到指標：{keyword}")
        return

    for iid, desc, path, unit, min_yr, max_yr in rows[:3]:
        print(f"指標：{desc}")
        print(f"路徑：{path}")
        print(f"期間：{min_yr} – {max_yr}，單位：{unit}\n")

        series = get_series(iid)
        if not series:
            print("  無時間序列數據\n")
            continue

        years = [r[3] for r in series]
        values = [r[1] for r in series]

        # Stats
        stats = compute_stats(values)
        print("【基本統計】")
        print(f"  最新值：{stats['latest']:,.2f}（{years[-1]}年）")
        print(f"  均值：{stats['mean']:,.2f}")
        print(f"  中位數：{stats['median']:,.2f}")
        print(f"  標準差：{stats['stdev']:,.2f}")
        print(f"  歷史區間：{stats['min']:,.2f} – {stats['max']:,.2f}")
        print(f"  長期變化：{stats['pct_change_total']:+.1f}%（{years[0]}→{years[-1]}）")
        print(f"  同比變化：{stats['pct_change_1y']:+.1f}%")

        # Trend
        trend = linear_trend(years, values)
        if trend:
            print(f"\n【趨勢】{trend['direction']}，年均變化：{trend['slope']:,.2f}/年")
            projected = trend['slope'] * (years[-1] + 1) + trend['intercept']
            print(f"  下一年度預測值：{projected:,.2f}")

        # Anomalies
        anomalies = detect_anomalies(values, years)
        if anomalies:
            print(f"\n【異常值】（偏離均值>1.5σ）")
            for yr, val, zscore in anomalies:
                print(f"  {yr}年：{val:,.2f}（z={zscore:+.1f}σ）")

        # Turning points
        turning = detect_turning_points(values, years)
        if turning:
            print(f"\n【拐點】")
            for yr, val, tp in turning[-5:]:
                print(f"  {yr}年：{val:,.2f}（{'峰' if tp == 'peak' else '谷'}）")

        print()


def cmd_trend(keyword: str):
    """Show trend chart for an indicator."""
    rows = find_indicators(keyword, limit=1)
    if not rows:
        print(f"未找到：{keyword}")
        return
    iid, desc, path, unit, *_ = rows[0]
    series = get_series(iid, 20)
    if not series:
        print("無數據")
        return

    years = [r[3] for r in series]
    values = [r[1] for r in series]

    trend = linear_trend(years, values)
    direction = trend['direction'] if trend else "unknown"

    # ASCII bar chart (last 15 years)
    print(f"\n=== {desc} ===")
    print(f"期間：{years[0]}–{years[-1]}，共{len(years)}年")
    print(f"趨勢：{direction}")
    if trend:
        print(f"年均變化：{trend['slope']:,.2f}/年\n")
    else:
        print()

    max_val = max(values)
    for yr, val in zip(years, values):
        bar_len = int(val / max_val * 40) if max_val else 0
        bar = "█" * bar_len
        pct = (val - values[0]) / values[0] * 100 if values[0] else 0
        print(f"  {yr} |{bar:40}| {val:>15,.2f} ({pct:+.1f}%)")


def cmd_compare(keyword1: str, keyword2: str):
    """Compare two indicators side by side."""
    rows1 = find_indicators(keyword1, limit=1)
    rows2 = find_indicators(keyword2, limit=1)
    if not rows1 or not rows2:
        print("未找到指標")
        return

    iid1, desc1 = rows1[0][0], rows1[0][1]
    iid2, desc2 = rows2[0][0], rows2[0][1]

    series1 = get_series(iid1, 10)
    series2 = get_series(iid2, 10)

    if not series1 or not series2:
        print("無時間序列")
        return

    print(f"\n=== {desc1} vs {desc2} ===\n")
    print(f"| 年份 | {desc1[:20]} | {desc2[:20]} | 相關性 |")
    print("|------|----------|----------|--------|")

    # Find overlapping years
    y1 = {r[3]: r[1] for r in series1}
    y2 = {r[3]: r[1] for r in series2}
    common = sorted(set(y1.keys()) & set(y2.keys()))

    if len(common) < 3:
        print("共同年份不足")
        return

    # Compute correlation
    vals1 = [y1[yr] for yr in common]
    vals2 = [y2[yr] for yr in common]
    import statistics
    mean1, mean2 = statistics.mean(vals1), statistics.mean(vals2)
    # Normalize first to avoid overflow
    z1 = [(v - mean1) / statistics.stdev(vals1) for v in vals1]
    z2 = [(v - mean2) / statistics.stdev(vals2) for v in vals2]
    corr = sum(a * b for a, b in zip(z1, z2)) / len(vals1)  # Pearson correlation

    for yr in common:
        print(f"| {yr} | {y1[yr]:,.2f} | {y2[yr]:,.2f} | {'正' if corr > 0 else '負'} {abs(corr):.2f}")

    print(f"\n皮爾遜相關系數：{corr:.3f}")
    if corr > 0.7:
        print("→ 兩指標高度正相關")
    elif corr > 0.4:
        print("→ 兩指標中度正相關")
    elif corr < -0.7:
        print("→ 兩指標高度負相關")
    elif corr < -0.4:
        print("→ 兩指標中度負相關")
    else:
        print("→ 兩指標相關性弱")


def cmd_llm(question: str):
    """Answer a natural language question about Macau macro data."""
    client = get_llm_client()
    if client is None:
        print("[錯誤] 未检测到 LLM API Key。請設定以下環境變量之一：")
        print("  export OPENROUTER_API_KEY=sk-or-v1-...")
        print("  export MINIMAX_API_KEY=sk-cp-...")
        print("  export HF_TOKEN=hf_...（需 Pro 帳戶）")
        print("\n或使用純 Python 分析：")
        print("  python3 macau_llm_analyzer.py analyze GDP")
        print("  python3 macau_llm_analyzer.py compare GDP 旅客")
        return

    # Build context
    keywords = ["GDP", "本地生產總值", "人口", "旅客", "博彩", "失業", "物價", "外勞", "貿易"]
    relevant = []
    for kw in keywords:
        if kw.lower() in question.lower():
            rows = find_indicators(kw, limit=2)
            relevant.extend(rows[:1])

    ctx = []
    for iid, desc, path, unit, *_ in relevant[:6]:
        series = get_series(iid, 10)
        if series:
            latest = series[-1]
            ctx.append(f"## {desc}（{path}）")
            for period, val, unit, year in series[-5:]:
                ctx.append(f"  {year}年: {val:,.2f}{(' '+unit) if unit else ''}")
            ctx.append("")

    context_text = "\n".join(ctx) if ctx else "（未找到相關指標數據）"

    prompt = f"""你是澳門宏觀經濟分析師。參考以下澳門統計數據回答問題：

{context_text}

問題：{question}

回答要求：
- 用中文，3-5段以內
- 引用具體數字
- 指出趨勢（上升/下降/持平）
- 注明數據年份"""

    print("思考中...\n")
    try:
        answer = llm_complete(prompt)
        print(f"\n回答：\n\n{answer}")
    except Exception as e:
        print(f"[錯誤：{e}]")


def cmd_update_wiki():
    """Update wiki concept pages with fresh analysis."""
    concept_map = [
        ("GDP-本地生產總值.md", "%人均本地生產總值%", "GDP — 本地生產總值"),
        ("人口.md", "%總人口%", "人口"),
        ("旅遊.md", "%入境旅客%留宿旅客%", "旅遊"),
        ("旅遊-博彩.md", "%博彩毛收入%", "旅遊-博彩"),
        ("就業-勞動力.md", "%失業率%", "就業-勞動力"),
        ("物價.md", "%消費物價指數按年變動%", "物價"),
        ("外地僱員.md", "%外地僱員%", "外地僱員"),
        ("對外貿易.md", "%對外商品貿易%總數%", "對外貿易"),
    ]

    client = get_llm_client()
    has_llm = client is not None
    print(f"LLM 可用：{has_llm}\n")

    for fname, pattern, name in concept_map:
        rows = find_indicators(pattern, limit=1)
        if not rows:
            print(f"  ⚠ {name}: 無指標")
            continue

        iid, desc, path, unit, *_ = rows[0]
        series = get_series(iid, 20)
        if not series:
            print(f"  ⚠ {name}: 無數據")
            continue

        years = [r[3] for r in series]
        values = [r[1] for r in series]
        stats = compute_stats(values)
        trend = linear_trend(years, values)
        anomalies = detect_anomalies(values, years)

        # Build analysis section
        analysis_parts = [
            f"**期間：** {years[0]}–{years[-1]}（共{len(years)}年）",
            f"**最新值：** {stats['latest']:,.2f}（{years[-1]}年）",
            f"**長期變化：** {stats['pct_change_total']:+.1f}%",
            f"**同比變化：** {stats['pct_change_1y']:+.1f}%",
        ]
        if trend:
            analysis_parts.append(f"**趨勢：** {trend['direction']}（年均 {trend['slope']:,.2f}）")
        if anomalies:
            anom_yrs = [str(yr) for yr, *_ in anomalies]
            analysis_parts.append(f"**異常年份：** {', '.join(anom_yrs)}")

        analysis_text = "\n\n".join(analysis_parts)

        # If LLM available, generate natural language summary
        if has_llm:
            print(f"  生成 LLM 摘要：{name}...", end=" ", flush=True)
            latest_5 = series[-5:]
            prompt = f"""澳門指標：{desc}
路徑：{path}
單位：{unit}

最新5年數據：
""" + "\n".join(f"{yr}年: {val:,.2f}" for _, val, unit, yr in latest_5) + f"""

請生成一段100字左右的**中文摘要**，描述這個指標的特徵和趨勢。只輸出摘要，不要標題。"""
            try:
                llm_summary = llm_complete(prompt)
                analysis_text += f"\n\n**LLM 分析：** {llm_summary}"
                print("✓")
            except Exception as e:
                print(f"✗ ({e})")

        fpath = WIKI_DIR / fname
        if fpath.exists():
            content = fpath.read_text(encoding='utf-8')
            # Update frontmatter
            if "updated:" in content:
                content = re.sub(r"updated: \d{4}-\d{2}-\d{2}", f"updated: {datetime.now().strftime('%Y-%m-%d')}", content)
            else:
                content = content.replace("---", "---\nupdated: " + datetime.now().strftime('%Y-%m-%d'), 1)

            # Replace or insert analysis section
            if "<!-- STATS -->" in content:
                content = re.sub(r"<!-- STATS -->.*?(<!-- /STATS -->)", f"<!-- STATS -->\n\n{analysis_text}\n\n<!-- /STATS -->", content, flags=re.DOTALL)
            else:
                # Append at end
                content += f"\n\n<!-- STATS -->\n\n{analysis_text}\n\n<!-- /STATS -->\n"

            fpath.write_text(content, encoding='utf-8')

        print(f"  ✓ {name}")

    print(f"\n完成！")


# ── CLI ────────────────────────────────────────────────────────────
USAGE = """
澳門宏觀經濟維基分析器

用法:
  python3 macau_llm_analyzer.py analyze <關鍵詞>   # 統計分析
  python3 macau_llm_analyzer.py trend <關鍵詞>     # 趨勢圖
  python3 macau_llm_analyzer.py compare <詞1> <詞2> # 對比
  python3 macau_llm_analyzer.py llm <問題>          # LLM問答
  python3 macau_llm_analyzer.py update-wiki         # 更新維基頁面

LLM API 設定（可選）:
  export OPENROUTER_API_KEY=sk-or-v1-...   # OpenRouter（推薦）
  export MINIMAX_API_KEY=sk-cp-...         # MiniMax
  export HF_TOKEN=hf_...                   # HuggingFace（需Pro）

示例:
  python3 macau_llm_analyzer.py analyze GDP
  python3 macau_llm_analyzer.py trend 失業率
  python3 macau_llm_analyzer.py compare GDP 旅客
  python3 macau_llm_analyzer.py llm "澳門2024年經濟怎樣？"
"""

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(USAGE)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "analyze":
        keyword = sys.argv[2] if len(sys.argv) > 2 else "GDP"
        cmd_analyze(keyword)

    elif cmd == "trend":
        keyword = sys.argv[2] if len(sys.argv) > 2 else "GDP"
        cmd_trend(keyword)

    elif cmd == "compare":
        if len(sys.argv) < 4:
            print("用法：compare <詞1> <詞2>")
            sys.exit(1)
        cmd_compare(sys.argv[2], sys.argv[3])

    elif cmd == "llm":
        question = " ".join(sys.argv[2:])
        if not question:
            print("請提供問題")
            sys.exit(1)
        cmd_llm(question)

    elif cmd == "update-wiki":
        cmd_update_wiki()

    else:
        print(USAGE)
