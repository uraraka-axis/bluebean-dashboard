"""
BlueBean CSV処理モジュール
CSVファイル（Shift_JIS）を読み込んでdashboard.json形式に変換

scripts/process-csv.js のPython版
"""

import csv
import io
import json
import os
from datetime import datetime, date
from calendar import monthrange

# --- 定数 ---
TRANSFER_PHONE_WEEKDAY = '8075810552'  # 平日転送先（携帯）
ACD_NAMES = {'8002': 'tablet', '8003': 'comic', '8004': 'other'}
DOW_NAMES = ['月', '火', '水', '木', '金', '土', '日']  # Python: 0=月曜


def read_csv_bytes(raw_bytes):
    """バイト列からCSVを読み込む（Shift_JIS対応）"""
    try:
        text = raw_bytes.decode('cp932')
    except UnicodeDecodeError:
        text = raw_bytes.decode('utf-8')

    if text.startswith('<') or '<!DOCTYPE' in text[:500]:
        return None

    # BOM除去
    if text.startswith('\ufeff'):
        text = text[1:]

    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def get_col(row, keyword):
    """CSV列名のあいまい検索"""
    for key in row:
        if keyword in key:
            return row[key]
    return None


def get_col_int(row, keyword, default=0):
    """あいまい検索 + int変換"""
    val = get_col(row, keyword)
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def time_to_sec(t):
    """HH:MM:SS → 秒"""
    if not t or t == '-':
        return 0
    parts = t.split(':')
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return 0
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    return 0


def sec_to_min_sec(s):
    """秒 → M:SS"""
    m = int(s) // 60
    sec = int(s) % 60
    return f"{m}:{sec:02d}"


def rate_class(rate):
    if rate >= 80:
        return 'good'
    if rate >= 65:
        return 'warn'
    return 'bad'


def _parse_transfer_record(row):
    """CDR行から転送レコードを生成（共通処理）"""
    dt_str = get_col(row, '発着信時間') or ''
    status = get_col(row, '状態') or ''
    talk_time = get_col(row, '通話時間') or '0'
    try:
        talk_int = int(talk_time)
    except ValueError:
        talk_int = time_to_sec(talk_time)

    # 曜日判定
    dow = None
    if len(dt_str) >= 10:
        try:
            dt = date(int(dt_str[:4]), int(dt_str[5:7]), int(dt_str[8:10]))
            dow = dt.weekday()  # 0=月
        except (ValueError, IndexError):
            pass

    return {
        'datetime': dt_str,
        'date': dt_str[:10],
        'hour': int(dt_str[11:13]) if len(dt_str) >= 13 else 0,
        'answered': status == '完了' or (talk_int > 0 and status != 'キャンセル'),
        'dow': dow,
    }


def extract_transfers_weekday(cdr_rows):
    """平日転送: PV発信 + 着信先に携帯番号を含む"""
    if not cdr_rows:
        return []
    results = []
    for row in cdr_rows:
        type_val = get_col(row, '種類') or ''
        dest = get_col(row, '着信先') or ''
        if 'PV発信' in type_val and TRANSFER_PHONE_WEEKDAY in dest:
            results.append(_parse_transfer_record(row))
    return results


def extract_transfers_saturday(cdr_rows):
    """土曜転送: PV発信 + 発着信時間が土曜日"""
    if not cdr_rows:
        return []
    results = []
    for row in cdr_rows:
        type_val = get_col(row, '種類') or ''
        if 'PV発信' in type_val:
            rec = _parse_transfer_record(row)
            if rec['dow'] == 5:  # 5=土曜
                results.append(rec)
    return results


def process_daily_summary(summary_rows, transfers, year, month):
    """日別集計"""
    if not summary_rows:
        return []
    days_in_month = monthrange(year, month)[1]
    results = []

    for d in range(1, days_in_month + 1):
        row = None
        for r in summary_rows:
            day_col = get_col(r, '日')
            if day_col:
                try:
                    if int(day_col) == d:
                        row = r
                        break
                except ValueError:
                    pass

        date_str = f"{year}-{month:02d}-{d:02d}"
        dt = date(year, month, d)
        dow = dt.weekday()  # 0=月曜

        calls = get_col_int(row, 'ACD着信') if row else 0
        answered = get_col_int(row, 'OP応答') if row else 0
        abandoned = get_col_int(row, '放棄') or (get_col_int(row, '顧客切断') if row else 0) if row else 0
        overflow = get_col_int(row, '溢れ') if row else 0
        rate = round(answered / calls * 100, 1) if calls > 0 else 0

        day_transfers = [t for t in transfers if t['date'] == date_str]

        # Python weekday: 0=月 → JS互換: 0=日に変換
        js_dow = (dow + 1) % 7

        results.append({
            'date': date_str,
            'day': d,
            'dow': js_dow,
            'dowName': DOW_NAMES[dow],
            'calls': calls,
            'answered': answered,
            'rate': rate,
            'rateClass': rate_class(rate) if calls > 0 else '',
            'abandoned': abandoned,
            'abandonRate': round(abandoned / calls * 100, 1) if calls > 0 else 0,
            'overflow': overflow,
            'transferCount': len(day_transfers),
        })

    return results


def process_acd_report(acd_rows):
    """ACD別集計"""
    if not acd_rows:
        return []
    results = []
    for row in acd_rows:
        group_col = get_col(row, 'グループ') or ''
        import re
        match = re.search(r'\d+', group_col)
        group_id = get_col(row, '番号') or (match.group(0) if match else '')
        name = get_col(row, '名') or ACD_NAMES.get(group_id, group_id)

        calls = get_col_int(row, 'ACD着信')
        answered = get_col_int(row, 'OP応答')
        abandoned = get_col_int(row, '顧客切断') or get_col_int(row, '放棄')
        overflow = get_col_int(row, '溢れ')
        rate = round(answered / calls * 100, 1) if calls > 0 else 0
        abandon_rate = round(abandoned / calls * 100, 1) if calls > 0 else 0

        avg_talk = get_col(row, '通話時間平均') or get_col(row, '通話時間') or '00:00:00'
        avg_wait = get_col(row, '待ち時間平均') or get_col(row, '待ち時間') or '00:00:00'

        result = {
            'groupId': group_id,
            'name': ACD_NAMES.get(group_id, name),
            'calls': calls,
            'answered': answered,
            'rate': rate,
            'rateClass': rate_class(rate),
            'abandoned': abandoned,
            'abandonRate': abandon_rate,
            'overflow': overflow,
            'avgTalkTime': avg_talk,
            'avgWaitTime': avg_wait,
        }
        if calls > 0 or result['name'] in ACD_NAMES.values():
            results.append(result)
    return results


def process_agent_report(agent_rows):
    """オペレーター別集計"""
    if not agent_rows:
        return []
    results = []
    for row in agent_rows:
        name = get_col(row, '名前') or get_col(row, '名') or ''
        if not name:
            continue
        login_id = get_col(row, 'ログインID') or ''
        talk_count = get_col_int(row, '通話回数')
        talk_time_str = get_col(row, '通話時間合計') or get_col(row, '通話時間') or '00:00:00'
        after_work_str = get_col(row, '後処理時間合計') or get_col(row, '後処理時間') or '00:00:00'
        after_count = get_col_int(row, '後処理回数') or talk_count
        break_time_str = get_col(row, '休憩時間合計') or '00:00:00'
        break_avg_str = get_col(row, '休憩時間平均') or '00:00:00'

        talk_sec = time_to_sec(talk_time_str)
        avg_talk_sec = round(talk_sec / talk_count) if talk_count > 0 else 0
        after_sec = time_to_sec(after_work_str)
        avg_after_sec = round(after_sec / after_count) if after_count > 0 else 0

        results.append({
            'loginId': login_id,
            'name': name,
            'talkCount': talk_count,
            'talkTimeTotal': talk_time_str,
            'avgTalkTime': sec_to_min_sec(avg_talk_sec),
            'afterWorkTotal': after_work_str,
            'avgAfterWork': sec_to_min_sec(avg_after_sec),
            'breakTimeTotal': break_time_str,
            'breakTimeAvg': break_avg_str,
        })
    return results


def calc_dow_average(daily_data):
    """曜日別平均計算"""
    dow_totals = {d: 0 for d in DOW_NAMES}
    dow_counts = {d: 0 for d in DOW_NAMES}
    for day in daily_data:
        if day['calls'] > 0:
            dow_totals[day['dowName']] += day['calls']
            dow_counts[day['dowName']] += 1
    result = {}
    for d in DOW_NAMES:
        if dow_counts[d] > 0:
            result[d] = round(dow_totals[d] / dow_counts[d], 1)
        else:
            result[d] = None
    return result


def build_dashboard(cur_files, prev_files, cur_year, cur_month, prev_year, prev_month):
    """
    dashboard.jsonの構造を構築

    cur_files / prev_files: dict with keys 'acd_summary', 'acd_report', 'cdr', 'agent_report'
        各値は read_csv_bytes() の結果（list[dict]）または None
    """
    now = datetime.now()
    ym = f"{cur_year}-{cur_month:02d}"
    prev_ym = f"{prev_year}-{prev_month:02d}"

    # 転送データ抽出（平日・土曜別）
    cur_transfers = extract_transfers_weekday(cur_files.get('cdr'))
    prev_transfers = extract_transfers_weekday(prev_files.get('cdr'))
    cur_transfers_sat = extract_transfers_saturday(cur_files.get('cdr'))
    prev_transfers_sat = extract_transfers_saturday(prev_files.get('cdr'))

    # 日別集計
    cur_daily = process_daily_summary(cur_files.get('acd_summary'), cur_transfers, cur_year, cur_month)
    prev_daily = process_daily_summary(prev_files.get('acd_summary'), prev_transfers, prev_year, prev_month)

    # 集計値計算ヘルパー
    def calc_summary(daily, transfers):
        active_days = len([d for d in daily if d['calls'] > 0])
        total_calls = sum(d['calls'] for d in daily)
        total_answered = sum(d['answered'] for d in daily)
        total_rate = round(total_answered / total_calls * 100, 1) if total_calls > 0 else 0
        daily_avg = round(total_calls / active_days, 1) if active_days > 0 else 0

        transfer_total = len(transfers)
        transfer_days = len(set(t['date'] for t in transfers))
        transfer_avg = round(transfer_total / transfer_days, 1) if transfer_days > 0 else 0
        transfer_answered = len([t for t in transfers if t['answered']])
        transfer_rate = round(transfer_answered / transfer_total * 100, 1) if transfer_total > 0 else 0

        return {
            'bb': {'total': total_calls, 'dailyAvg': daily_avg, 'rate': total_rate, 'activeDays': active_days},
            'transfer': {'total': transfer_total, 'dailyAvg': transfer_avg, 'rate': transfer_rate},
        }

    cur_summary = calc_summary(cur_daily, cur_transfers)
    prev_summary = calc_summary(prev_daily, prev_transfers)

    # 土曜転送サマリー
    def calc_transfer_summary(transfers):
        total = len(transfers)
        days = len(set(t['date'] for t in transfers))
        avg = round(total / days, 1) if days > 0 else 0
        answered = len([t for t in transfers if t['answered']])
        rate = round(answered / total * 100, 1) if total > 0 else 0
        return {'total': total, 'dailyAvg': avg, 'rate': rate}

    cur_sat_summary = calc_transfer_summary(cur_transfers_sat)
    prev_sat_summary = calc_transfer_summary(prev_transfers_sat)

    # 昨日データ
    yesterday_data = None
    for d in cur_daily:
        if d['day'] == now.day - 1:
            yesterday_data = d
            break

    # ACD別
    cur_acd = process_acd_report(cur_files.get('acd_report'))
    prev_acd = process_acd_report(prev_files.get('acd_report'))

    cur_active = cur_summary['bb']['activeDays'] or 1
    prev_active = prev_summary['bb']['activeDays'] or 1
    for a in cur_acd:
        a['dailyAvg'] = round(a['calls'] / cur_active, 1)
    for a in prev_acd:
        a['dailyAvg'] = round(a['calls'] / prev_active, 1)

    # オペレーター別
    cur_agents = process_agent_report(cur_files.get('agent_report'))
    prev_agents = process_agent_report(prev_files.get('agent_report'))
    for a in cur_agents:
        a['dailyAvg'] = round(a['talkCount'] / cur_active, 1)
    for a in prev_agents:
        a['dailyAvg'] = round(a['talkCount'] / prev_active, 1)

    # 曜日別平均
    cur_dow = calc_dow_average(cur_daily)
    prev_dow = calc_dow_average(prev_daily)

    return {
        'generated': now.isoformat(),
        'source': 'manual_import',
        'currentMonth': {'year': cur_year, 'month': cur_month, 'ym': ym, 'label': f'{cur_month}月'},
        'prevMonth': {'year': prev_year, 'month': prev_month, 'ym': prev_ym, 'label': f'{prev_month}月'},
        'yesterday': yesterday_data,
        'bbSummary': {
            'current': cur_summary['bb'],
            'prev': prev_summary['bb'],
        },
        'transferSummary': {
            'current': cur_summary['transfer'],
            'prev': prev_summary['transfer'],
        },
        'daily': {'current': list(reversed(cur_daily)), 'prev': list(reversed(prev_daily))},
        'acd': {'current': cur_acd, 'prev': prev_acd},
        'acdTransfer': {
            'current': cur_summary['transfer'],
            'prev': prev_summary['transfer'],
        },
        'saturdayTransfer': {
            'current': cur_sat_summary,
            'prev': prev_sat_summary,
        },
        'dowAverage': {'current': cur_dow, 'prev': prev_dow},
        'agents': {'current': cur_agents, 'prev': prev_agents},
    }
