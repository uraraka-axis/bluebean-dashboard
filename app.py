"""
BlueBeanダッシュボード - Streamlit版
data/dashboard.json を読み込んで表示
"""

import json
import os
from datetime import datetime, date
import streamlit as st
import pandas as pd
import csv_processor

st.set_page_config(
    page_title="BlueBeanダッシュボード",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- パスワード認証 ---
def check_password():
    if st.session_state.get("authenticated"):
        return True

    _, col, _ = st.columns([1, 1, 1])
    with col:
        password = st.text_input("パスワード", type="password")
        if st.button("ログイン", use_container_width=True):
            if password == st.secrets.get("auth", {}).get("password", ""):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("パスワードが正しくありません")
    return False


if not check_password():
    st.stop()

# --- カスタムCSS ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+JP:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', 'Noto Sans JP', sans-serif;
}

/* Streamlitデフォルト余白を詰める */
.block-container { padding-top: 1rem !important; }
header[data-testid="stHeader"] { display: none !important; }

/* ヘッダー */
.main-header {
    background: linear-gradient(135deg, #1e3a5f 0%, #1a56db 100%);
    color: white;
    padding: 16px 24px;
    border-radius: 8px;
    margin-bottom: 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.main-header h1 { margin: 0; font-size: 20px; font-weight: 700; }
.main-header .meta { font-size: 12px; opacity: 0.8; }

/* KPIカード */
.kpi-card {
    background: white;
    border-radius: 12px;
    padding: 20px;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    border: 1px solid #e5e7eb;
}
.kpi-card .label { font-size: 13px; color: #6b7280; margin-bottom: 4px; }
.kpi-card .value { font-size: 28px; font-weight: 700; color: #111827; }
.kpi-card .sub { font-size: 13px; color: #6b7280; margin-top: 4px; }
.kpi-card .value.good { color: #059669; }
.kpi-card .value.warn { color: #d97706; }
.kpi-card .value.bad { color: #dc2626; }

/* 昨日カード */
.yesterday-card {
    background: white;
    border-radius: 12px;
    padding: 20px;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    border-left: 4px solid #6366f1;
}
.yesterday-card .label { font-size: 13px; color: #6b7280; }
.yesterday-card .value { font-size: 32px; font-weight: 700; color: #111827; }
.yesterday-card .rate { font-size: 14px; font-weight: 600; }

/* セクション */
.section-card {
    background: white;
    border-radius: 12px;
    padding: 24px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    border: 1px solid #e5e7eb;
    margin-bottom: 16px;
}
.section-title {
    font-size: 16px;
    font-weight: 600;
    color: #374151;
    border-left: 4px solid #1a56db;
    padding-left: 12px;
    margin-bottom: 16px;
}

/* 応答率バー */
.rate-bar-bg {
    display: inline-block;
    width: 80px;
    height: 8px;
    border-radius: 4px;
    margin-right: 8px;
    vertical-align: middle;
}
.rate-bar-fill {
    display: block;
    height: 8px;
    border-radius: 4px;
}

/* テーブル */
.styled-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.styled-table th {
    background: #f9fafb;
    color: #6b7280;
    font-weight: 500;
    padding: 12px 14px;
    text-align: right;
    border-bottom: 2px solid #e5e7eb;
}
.styled-table th:first-child { text-align: left; }
.styled-table td {
    padding: 12px 14px;
    text-align: right;
    border-bottom: 1px solid #f3f4f6;
}
.styled-table td:first-child { text-align: left; font-weight: 500; }
.styled-table tr:hover { background: #f9fafb; }

/* 放棄率バッジ */
.badge-red { background: #fef2f2; color: #dc2626; padding: 2px 8px; border-radius: 10px; font-size: 13px; font-weight: 600; }
.badge-orange { background: #fffbeb; color: #d97706; padding: 2px 8px; border-radius: 10px; font-size: 13px; font-weight: 600; }
.badge-green { background: #f0fdf4; color: #059669; padding: 2px 8px; border-radius: 10px; font-size: 13px; font-weight: 600; }

/* ACD カード */
.acd-card {
    background: white;
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    border: 1px solid #e5e7eb;
}
.acd-card .acd-name { font-size: 15px; font-weight: 600; margin-bottom: 12px; }
.acd-metric { display: flex; justify-content: space-between; margin-bottom: 8px; }
.acd-metric .label { font-size: 12px; color: #6b7280; }
.acd-metric .value { font-size: 16px; font-weight: 700; }

/* Streamlit要素の調整 */
.stTabs [data-baseweb="tab-list"] { gap: 0; }
.stTabs [data-baseweb="tab"] {
    padding: 12px 24px;
    font-weight: 500;
    font-size: 14px;
}
div[data-testid="stMetricValue"] { font-size: 24px; }
</style>
""", unsafe_allow_html=True)


# --- データ読み込み ---
@st.cache_data(ttl=300)
def load_data():
    json_path = os.path.join(os.path.dirname(__file__), "data", "dashboard.json")
    if not os.path.exists(json_path):
        return None
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def rate_color(rate):
    if rate >= 80:
        return "good", "#059669"
    if rate >= 65:
        return "warn", "#d97706"
    return "bad", "#dc2626"


def rate_bar_html(rate):
    cls, color = rate_color(rate)
    width = min(rate, 100)
    bg = "#fee2e2" if cls == "bad" else ("#fef3c7" if cls == "warn" else "#d1fae5")
    return f'<span class="rate-bar-bg" style="background:{bg}"><span class="rate-bar-fill" style="width:{width * 0.8}px;background:{color}"></span></span>{rate}%'


def abandon_badge(rate):
    if rate >= 20:
        return f'<span class="badge-red">{rate}%</span>'
    if rate >= 10:
        return f'<span class="badge-orange">{rate}%</span>'
    return f'<span class="badge-green">{rate}%</span>'


def format_dow_name(dow_name):
    if dow_name == "日":
        return f'<span style="color:#dc2626">{dow_name}</span>'
    if dow_name == "土":
        return f'<span style="color:#2563eb">{dow_name}</span>'
    return dow_name


# --- メイン ---
data = load_data()

if data is None:
    st.error("データが見つかりません。data/dashboard.json を確認してください。")
    st.stop()

cur_month = data["currentMonth"]
prev_month = data["prevMonth"]
generated = data.get("generated", "")

# ヘッダー
gen_display = ""
if generated:
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(generated.replace("Z", "+00:00"))
        gen_display = f"{dt.year}年{dt.month}月{dt.day}日 {dt.strftime('%H:%M')}"
    except Exception:
        gen_display = generated[:16]

st.markdown(f"""
<div class="main-header">
    <h1>BlueBeanダッシュボード</h1>
    <div class="meta">最終更新: {gen_display} ／ データ取得: {'手動インポート' if data.get('source') == 'manual_import' else '自動（日次）'}</div>
</div>
""", unsafe_allow_html=True)

# タブ
tab_overall, tab_acd, tab_operator, tab_import = st.tabs(["全体", "ACD別", "オペレーター別", "データインポート"])


# ==================== 全体タブ ====================
with tab_overall:
    # 昨日カード
    yd = data.get("yesterday")
    if yd and yd.get("calls", 0) > 0:
        _, col_yd, _ = st.columns([1, 2, 1])
        with col_yd:
            rate_cls, rate_col = rate_color(yd["rate"])
            st.markdown(f"""
            <div class="yesterday-card">
                <div class="label">昨日（{yd['date'][5:]}（{yd['dowName']}））</div>
                <div class="value">{yd['calls']}<span style="font-size:16px;color:#6b7280"> 件</span></div>
                <div class="rate" style="color:{rate_col}">応答率 {yd['rate']}%</div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("")

    # BB受電サマリー
    st.markdown('<div class="section-title">BB受電サマリー（9:00〜17:00 BlueBeanオペレーター対応分）</div>', unsafe_allow_html=True)
    bb = data["bbSummary"]

    cols = st.columns(6)
    bb_items = [
        ("今月合計", str(bb["current"]["total"]), ""),
        ("今月1日平均", str(bb["current"]["dailyAvg"]), ""),
        ("今月応答率", f'{bb["current"]["rate"]}%', rate_color(bb["current"]["rate"])[0]),
        (f'先月合計（{prev_month["label"]}）', str(bb["prev"]["total"]), ""),
        (f'先月1日平均（{prev_month["label"]}）', str(bb["prev"]["dailyAvg"]), ""),
        (f'先月応答率（{prev_month["label"]}）', f'{bb["prev"]["rate"]}%', rate_color(bb["prev"]["rate"])[0] if bb["prev"]["rate"] > 0 else ""),
    ]
    for i, (label, value, cls) in enumerate(bb_items):
        with cols[i]:
            color_style = ""
            if cls == "good":
                color_style = "color:#059669"
            elif cls == "warn":
                color_style = "color:#d97706"
            elif cls == "bad":
                color_style = "color:#dc2626"
            st.markdown(f"""
            <div class="kpi-card">
                <div class="label">{label}</div>
                <div class="value" style="{color_style}">{value}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("")

    # 転送受電サマリー
    st.markdown('<div class="section-title">17時以降転送受電サマリー（17:00〜19:00 携帯転送分）</div>', unsafe_allow_html=True)
    tr = data["transferSummary"]

    cols = st.columns(6)
    tr_items = [
        ("今月合計", str(tr["current"]["total"]), ""),
        ("今月1日平均", str(tr["current"]["dailyAvg"]), ""),
        ("今月応答率", f'{tr["current"]["rate"]}%', rate_color(tr["current"]["rate"])[0] if tr["current"]["rate"] > 0 else ""),
        (f'先月合計（{prev_month["label"]}）', str(tr["prev"]["total"]), ""),
        (f'先月1日平均（{prev_month["label"]}）', str(tr["prev"]["dailyAvg"]), ""),
        (f'先月応答率（{prev_month["label"]}）', f'{tr["prev"]["rate"]}%', rate_color(tr["prev"]["rate"])[0] if tr["prev"]["rate"] > 0 else ""),
    ]
    for i, (label, value, cls) in enumerate(tr_items):
        with cols[i]:
            color_style = ""
            if cls == "good":
                color_style = "color:#059669"
            elif cls == "warn":
                color_style = "color:#d97706"
            elif cls == "bad":
                color_style = "color:#dc2626"
            st.markdown(f"""
            <div class="kpi-card">
                <div class="label">{label}</div>
                <div class="value" style="{color_style}">{value}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("")

    # 日別実績一覧
    st.markdown('<div class="section-title">日別実績一覧</div>', unsafe_allow_html=True)
    month_sel = st.radio(
        "月選択", [f'今月（{cur_month["label"]}）', f'先月（{prev_month["label"]}）'],
        horizontal=True, key="daily_month", label_visibility="collapsed"
    )
    daily_key = "current" if "今月" in month_sel else "prev"
    daily = data["daily"][daily_key]

    # 受電のある日のみ表示
    daily_active = [d for d in daily if d["calls"] > 0]

    if daily_active:
        header = "<tr><th>日付</th><th>受電数</th><th>応答数</th><th>応答率</th><th>放棄数</th><th>放棄率</th><th>溢れ呼</th><th>転送受電</th></tr>"
        rows = ""
        for d in daily_active:
            dow_html = format_dow_name(d["dowName"])
            rate_html = rate_bar_html(d["rate"])
            abandon_html = abandon_badge(d["abandonRate"]) if d["abandonRate"] > 0 else f'<span class="badge-green">0%</span>'
            transfer = str(d["transferCount"]) if d["transferCount"] > 0 else "-"
            rows += f"""<tr>
                <td>{d['date'][5:]}（{dow_html}）</td>
                <td>{d['calls']}</td><td>{d['answered']}</td>
                <td>{rate_html}</td>
                <td>{d['abandoned']}</td><td>{abandon_html}</td>
                <td>{d['overflow']}</td><td>{transfer}</td>
            </tr>"""

        st.markdown(f'<table class="styled-table">{header}{rows}</table>', unsafe_allow_html=True)
        st.caption("※ 転送受電 = 平日17:00〜19:00の携帯転送分。土曜は第1=BB対応、第2=休、第3〜5=転送。")
    else:
        st.info("データがありません。")


# ==================== ACD別タブ ====================
with tab_acd:
    acd_month_sel = st.radio(
        "月選択", [f'今月（{cur_month["label"]}）', f'先月（{prev_month["label"]}）'],
        horizontal=True, key="acd_month", label_visibility="collapsed"
    )
    acd_key = "current" if "今月" in acd_month_sel else "prev"
    acd_month_label = cur_month["label"] if acd_key == "current" else prev_month["label"]
    acd_list = data["acd"][acd_key]
    acd_transfer = data["acdTransfer"][acd_key]
    sat_transfer = data.get("saturdayTransfer", {}).get(acd_key, {"total": 0, "dailyAvg": 0, "rate": 0})
    bb_summary = data["bbSummary"][acd_key]
    active_days = bb_summary.get("activeDays", 1) or 1

    # ACDカード
    st.markdown(f'<div class="section-title">ACD別 サマリー（{acd_month_label}）</div>', unsafe_allow_html=True)

    if acd_list:
        cols = st.columns(len(acd_list))
        acd_colors = {"tablet": "#3b82f6", "comic": "#8b5cf6", "other": "#f59e0b"}

        for i, acd in enumerate(acd_list):
            with cols[i]:
                color = acd_colors.get(acd["name"], "#6b7280")
                rate_cls, rate_col = rate_color(acd["rate"])
                st.markdown(f"""
                <div class="acd-card">
                    <div class="acd-name"><span style="color:{color}">●</span> {acd['name']}（{acd['groupId']}）</div>
                    <div style="display:flex;gap:8px;margin-bottom:8px">
                        <div style="flex:1;text-align:center">
                            <div style="display:flex;justify-content:space-around;margin-top:4px">
                                <div><div style="font-size:20px;font-weight:700">{acd['calls']}</div><div style="font-size:11px;color:#6b7280">受電数</div></div>
                                <div><div style="font-size:20px;font-weight:700">{acd['dailyAvg']}</div><div style="font-size:11px;color:#6b7280">1日平均</div></div>
                                <div><div style="font-size:20px;font-weight:700;color:{rate_col}">{acd['rate']}%</div><div style="font-size:11px;color:#6b7280">応答率</div></div>
                                <div><div style="font-size:20px;font-weight:700;color:{'#dc2626' if acd['abandonRate']>=20 else '#d97706' if acd['abandonRate']>=10 else '#059669'}">{acd['abandonRate']}%</div><div style="font-size:11px;color:#6b7280">放棄率</div></div>
                            </div>
                        </div>
                    </div>
                    <div style="font-size:12px;color:#6b7280;border-top:1px solid #e5e7eb;padding-top:8px">
                        平均通話時間: {acd['avgTalkTime']}
                    </div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("")

    # ACD別テーブル
    st.markdown(f'<div class="section-title">ACD別 実績一覧（{acd_month_label}）</div>', unsafe_allow_html=True)

    if acd_list:
        header = "<tr><th>ACDグループ</th><th>受電数</th><th>1日平均</th><th>応答数</th><th>応答率</th><th>放棄数</th><th>放棄率</th><th>溢れ呼</th><th>平均通話時間</th></tr>"
        rows = ""
        acd_colors_dot = {"tablet": "#3b82f6", "comic": "#8b5cf6", "other": "#f59e0b"}
        for acd in acd_list:
            color = acd_colors_dot.get(acd["name"], "#6b7280")
            rate_html = rate_bar_html(acd["rate"])
            abandon_html = abandon_badge(acd["abandonRate"])
            rows += f"""<tr>
                <td><span style="color:{color}">●</span> {acd['name']}</td>
                <td>{acd['calls']}</td><td>{acd['dailyAvg']}</td><td>{acd['answered']}</td>
                <td>{rate_html}</td>
                <td>{acd['abandoned']}</td><td>{abandon_html}</td><td>{acd['overflow']}</td>
                <td>{acd['avgTalkTime']}</td>
            </tr>"""

        # 転送行（平日）
        transfer_rate_html = rate_bar_html(acd_transfer["rate"]) if acd_transfer["total"] > 0 else "-%"
        transfer_abandon = acd_transfer["total"] - int(acd_transfer["total"] * acd_transfer["rate"] / 100) if acd_transfer["total"] > 0 else 0
        transfer_abandon_rate = round((1 - acd_transfer["rate"] / 100) * 100, 1) if acd_transfer["total"] > 0 else 0
        rows += f"""<tr>
            <td style="color:#6366f1">転送（平日）</td>
            <td style="color:#6366f1">{acd_transfer['total']}</td>
            <td style="color:#6366f1">{acd_transfer['dailyAvg']}</td>
            <td>{int(acd_transfer['total'] * acd_transfer['rate'] / 100) if acd_transfer['total'] > 0 else 0}</td>
            <td>{transfer_rate_html}</td>
            <td>{transfer_abandon}</td><td>{abandon_badge(transfer_abandon_rate) if acd_transfer['total'] > 0 else '-'}</td>
            <td>-</td>
        </tr>"""

        # 転送行（土曜）
        sat_rate_html = rate_bar_html(sat_transfer["rate"]) if sat_transfer["total"] > 0 else "-%"
        sat_abandon = sat_transfer["total"] - int(sat_transfer["total"] * sat_transfer["rate"] / 100) if sat_transfer["total"] > 0 else 0
        sat_abandon_rate = round((1 - sat_transfer["rate"] / 100) * 100, 1) if sat_transfer["total"] > 0 else 0
        rows += f"""<tr>
            <td style="color:#059669">転送（土曜）</td>
            <td style="color:#059669">{sat_transfer['total']}</td>
            <td style="color:#059669">{sat_transfer['dailyAvg']}</td>
            <td>{int(sat_transfer['total'] * sat_transfer['rate'] / 100) if sat_transfer['total'] > 0 else 0}</td>
            <td>{sat_rate_html}</td>
            <td>{sat_abandon}</td><td>{abandon_badge(sat_abandon_rate) if sat_transfer['total'] > 0 else '-'}</td>
            <td>-</td>
        </tr>"""

        st.markdown(f'<table class="styled-table">{header}{rows}</table>', unsafe_allow_html=True)

    st.markdown("")

    # 曜日別平均
    st.markdown(f'<div class="section-title">曜日別 平均受電数（{acd_month_label}）</div>', unsafe_allow_html=True)
    dow = data["dowAverage"][acd_key]

    dow_order = ["月", "火", "水", "木", "金", "土", "日"]
    header = "<tr><th>全体</th>" + "".join(f"<th>{format_dow_name(d)}</th>" for d in dow_order) + "</tr>"
    vals = "".join(f"<td>{dow.get(d, '-') if dow.get(d) is not None else '-'}</td>" for d in dow_order)
    rows = f"<tr><td><strong>合計</strong></td>{vals}</tr>"
    st.markdown(f'<table class="styled-table">{header}{rows}</table>', unsafe_allow_html=True)
    st.caption("※ 稼働日のみの平均。受電0件の日（休業日等）は除外。")


# ==================== オペレーター別タブ ====================
with tab_operator:
    agent_month_sel = st.radio(
        "月選択", [f'今月（{cur_month["label"]}）', f'先月（{prev_month["label"]}）'],
        horizontal=True, key="agent_month", label_visibility="collapsed"
    )
    agent_key = "current" if "今月" in agent_month_sel else "prev"
    agent_month_label = cur_month["label"] if agent_key == "current" else prev_month["label"]
    agents = data["agents"][agent_key]
    acd_transfer_agent = data["acdTransfer"][agent_key]

    # オペレーター別テーブル
    st.markdown(f'<div class="section-title">オペレーター別 実績（{agent_month_label}）</div>', unsafe_allow_html=True)

    if agents:
        # オペレーター→ACD名マッピング
        agent_acd_map = {
            "tablet1": "tablet", "tablet2": "tablet",
            "comic1": "comic", "comic2": "comic",
            "other": "other",
        }
        acd_colors_dot = {"tablet": "#3b82f6", "comic": "#8b5cf6", "other": "#f59e0b", "転送": "#6366f1"}

        header = "<tr><th>オペレーター</th><th>所属ACD</th><th>通話回数</th><th>1日平均</th><th>通話時間合計</th><th>平均通話時間</th><th>後処理時間合計</th><th>平均後処理時間</th><th>休憩合計</th><th>休憩平均</th></tr>"
        rows = ""
        for agent in agents:
            acd_name = agent_acd_map.get(agent["name"], agent["name"])
            color = acd_colors_dot.get(acd_name, "#6b7280")
            rows += f"""<tr>
                <td><strong>{agent['name']}</strong></td>
                <td><span style="color:{color}">●</span> {acd_name}</td>
                <td>{agent['talkCount']}</td><td>{agent['dailyAvg']}</td>
                <td>{agent['talkTimeTotal']}</td><td>{agent['avgTalkTime']}</td>
                <td>{agent['afterWorkTotal']}</td><td>{agent['avgAfterWork']}</td>
                <td>{agent.get('breakTimeTotal', '-')}</td><td>{agent.get('breakTimeAvg', '-')}</td>
            </tr>"""

        # 転送行（平日）
        rows += f"""<tr>
            <td style="color:#6366f1">転送（平日）</td>
            <td><span style="color:#6366f1">●</span> 転送</td>
            <td style="color:#6366f1">{acd_transfer_agent['total']}</td>
            <td style="color:#6366f1">{acd_transfer_agent['dailyAvg']}</td>
            <td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td>
        </tr>"""

        st.markdown(f'<table class="styled-table">{header}{rows}</table>', unsafe_allow_html=True)
        st.caption("※ 転送分はBlueBeanオペレーター外のため、通話時間等の詳細はCDRに記録なし。件数のみ集計。")
    else:
        st.info("データがありません。")

    st.markdown("")

    # 曜日別平均
    st.markdown(f'<div class="section-title">曜日別 平均通話回数（{agent_month_label}）</div>', unsafe_allow_html=True)
    dow_agent = data["dowAverage"][agent_key]

    dow_order = ["月", "火", "水", "木", "金", "土", "日"]
    header = "<tr><th>全体</th>" + "".join(f"<th>{format_dow_name(d)}</th>" for d in dow_order) + "</tr>"
    vals = "".join(f"<td>{dow_agent.get(d, '-') if dow_agent.get(d) is not None else '-'}</td>" for d in dow_order)
    rows = f"<tr><td><strong>合計</strong></td>{vals}</tr>"
    st.markdown(f'<table class="styled-table">{header}{rows}</table>', unsafe_allow_html=True)
    st.caption("※ 稼働日のみの平均。受電0件の日（休業日等）は除外。")


# ==================== データインポートタブ ====================
with tab_import:
    st.markdown('<div class="section-title">データインポート</div>', unsafe_allow_html=True)
    st.markdown("BlueBeanからダウンロードしたCSVファイル（Shift_JIS）をアップロードしてください。")

    st.markdown("")

    # 対象月の選択肢（過去6ヶ月分）
    today_d = date.today()
    month_options = []
    for offset in range(0, 6):
        y = today_d.year
        m = today_d.month - offset
        while m <= 0:
            m += 12
            y -= 1
        month_options.append(f"{y}年{m}月")

    col_cur, col_prev = st.columns(2)

    with col_cur:
        st.markdown("#### 今月データ")
        cur_month_sel = st.selectbox("対象月", month_options, index=0, key="cur_month_sel")
        cur_y = int(cur_month_sel.split("年")[0])
        cur_m = int(cur_month_sel.split("年")[1].replace("月", ""))

        st.markdown("")
        cur_summary_file = st.file_uploader("ACD日別サマリー", type=["csv"], key="cur_summary")
        cur_acd_file = st.file_uploader("ACD集計レポート", type=["csv"], key="cur_acd")
        cur_cdr_file = st.file_uploader("CDR発着信履歴", type=["csv"], key="cur_cdr")
        cur_agent_file = st.file_uploader("オペレーターレポート", type=["csv"], key="cur_agent")

    with col_prev:
        st.markdown("#### 先月データ")
        default_prev = 1 if len(month_options) > 1 else 0
        prev_month_sel = st.selectbox("対象月", month_options, index=default_prev, key="prev_month_sel")
        prev_y = int(prev_month_sel.split("年")[0])
        prev_m = int(prev_month_sel.split("年")[1].replace("月", ""))

        st.markdown("")
        prev_summary_file = st.file_uploader("ACD日別サマリー", type=["csv"], key="prev_summary")
        prev_acd_file = st.file_uploader("ACD集計レポート", type=["csv"], key="prev_acd")
        prev_cdr_file = st.file_uploader("CDR発着信履歴", type=["csv"], key="prev_cdr")
        prev_agent_file = st.file_uploader("オペレーターレポート", type=["csv"], key="prev_agent")

    st.markdown("---")

    # アップロード状況
    cur_files_uploaded = [f for f in [cur_summary_file, cur_acd_file, cur_cdr_file, cur_agent_file] if f]
    prev_files_uploaded = [f for f in [prev_summary_file, prev_acd_file, prev_cdr_file, prev_agent_file] if f]
    total_uploaded = len(cur_files_uploaded) + len(prev_files_uploaded)

    if total_uploaded > 0:
        status_parts = []
        if cur_files_uploaded:
            status_parts.append(f"今月: {len(cur_files_uploaded)}/4ファイル")
        if prev_files_uploaded:
            status_parts.append(f"先月: {len(prev_files_uploaded)}/4ファイル")
        st.info(f"アップロード済み — {' ／ '.join(status_parts)}")

    # 処理実行ボタン
    can_process = total_uploaded > 0
    if st.button("データを処理して更新", disabled=not can_process, type="primary", use_container_width=True):
        try:
            def parse_upload(file_obj):
                if file_obj is None:
                    return None
                return csv_processor.read_csv_bytes(file_obj.read())

            cur_csv = {
                'acd_summary': parse_upload(cur_summary_file),
                'acd_report': parse_upload(cur_acd_file),
                'cdr': parse_upload(cur_cdr_file),
                'agent_report': parse_upload(cur_agent_file),
            }
            prev_csv = {
                'acd_summary': parse_upload(prev_summary_file),
                'acd_report': parse_upload(prev_acd_file),
                'cdr': parse_upload(prev_cdr_file),
                'agent_report': parse_upload(prev_agent_file),
            }

            result = csv_processor.build_dashboard(cur_csv, prev_csv, cur_y, cur_m, prev_y, prev_m)

            # 未アップロード側は既存データで補完
            existing = load_data() or {}

            if not any(cur_csv.values()) and existing:
                for key in ['bbSummary', 'transferSummary', 'acdTransfer', 'saturdayTransfer']:
                    if key in existing:
                        result[key]['current'] = existing[key]['current']
                for key in ['daily', 'acd', 'agents', 'dowAverage']:
                    if key in existing:
                        result[key]['current'] = existing[key]['current']
                if 'yesterday' in existing:
                    result['yesterday'] = existing['yesterday']

            if not any(prev_csv.values()) and existing:
                for key in ['bbSummary', 'transferSummary', 'acdTransfer', 'saturdayTransfer']:
                    if key in existing:
                        result[key]['prev'] = existing[key]['prev']
                for key in ['daily', 'acd', 'agents', 'dowAverage']:
                    if key in existing:
                        result[key]['prev'] = existing[key]['prev']

            # dashboard.json に保存
            json_path = os.path.join(os.path.dirname(__file__), "data", "dashboard.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            st.cache_data.clear()

            st.success(f"データを更新しました（今月: {cur_y}年{cur_m}月 ／ 先月: {prev_y}年{prev_m}月）")

            # 結果プレビュー
            bb = result['bbSummary']['current']
            tr = result['transferSummary']['current']
            prev_bb = result['bbSummary']['prev']
            cols = st.columns(4)
            with cols[0]:
                st.metric("今月受電合計", bb['total'])
            with cols[1]:
                st.metric("今月応答率", f"{bb['rate']}%")
            with cols[2]:
                st.metric("今月転送件数", tr['total'])
            with cols[3]:
                st.metric("先月受電合計", prev_bb['total'])

            st.download_button(
                "dashboard.json をダウンロード",
                data=json.dumps(result, ensure_ascii=False, indent=2),
                file_name="dashboard.json",
                mime="application/json",
            )

        except Exception as e:
            st.error(f"処理エラー: {e}")

    if not can_process:
        st.caption("※ 最低1つのCSVファイルをアップロードしてください。")
