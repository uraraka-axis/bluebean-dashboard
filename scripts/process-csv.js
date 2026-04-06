/**
 * CSV → dashboard.json 集計スクリプト
 *
 * 入力: data/YYYY-MM/ 配下のCSV4種（今月 + 先月）
 * 出力: data/dashboard.json
 *
 * CSVはShift-JIS → UTF-8変換して読み込む
 */

const fs = require('fs');
const path = require('path');
const iconv = require('iconv-lite');
const { parse } = require('csv-parse/sync');

// --- 転送先電話番号 ---
const TRANSFER_PHONES = [
  '08075810552', '0463746531', '08035369556', '08032059925'
];

// --- ACD グループ名マッピング ---
const ACD_NAMES = { '8002': 'tablet', '8003': 'comic', '8004': 'other' };

// --- 曜日名 ---
const DOW_NAMES = ['日', '月', '火', '水', '木', '金', '土'];

function readCsvFile(filePath) {
  if (!fs.existsSync(filePath)) return null;
  const buf = fs.readFileSync(filePath);
  const text = iconv.decode(buf, 'Shift_JIS');
  return parse(text, { columns: true, skip_empty_lines: true, trim: true });
}

function findLatestCsv(dir, prefix) {
  if (!fs.existsSync(dir)) return null;
  const files = fs.readdirSync(dir)
    .filter(f => f.startsWith(prefix) && f.endsWith('.csv'))
    .sort()
    .reverse();
  return files.length > 0 ? path.join(dir, files[0]) : null;
}

// 月の稼働日数を計算（受電数 > 0 の日数）
function countActiveDays(dailyRows) {
  return dailyRows.filter(r => {
    const calls = parseInt(getCol(r, 'ACD着信') || '0');
    return calls > 0;
  }).length;
}

// CSV列名のあいまい検索（Shift-JIS変換で化けることがあるため）
function getCol(row, keyword) {
  const keys = Object.keys(row);
  const key = keys.find(k => k.includes(keyword));
  return key ? row[key] : undefined;
}

// 時刻文字列 "HH:MM:SS" → 秒
function timeToSec(t) {
  if (!t || t === '-') return 0;
  const parts = t.split(':').map(Number);
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return 0;
}

// 秒 → "M:SS"
function secToMinSec(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
}

// 秒 → "H:MM:SS"
function secToHMS(s) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

// 応答率の色分け
function rateClass(rate) {
  if (rate >= 80) return 'good';
  if (rate >= 65) return 'warn';
  return 'bad';
}

// --- CDRから転送データを抽出 ---
function extractTransfers(cdrRows) {
  if (!cdrRows) return [];
  return cdrRows.filter(row => {
    const type = getCol(row, '種類') || '';
    const operator = getCol(row, 'オペレータ') || '';
    const dest = getCol(row, '着信先') || '';
    return type.includes('PV発信') && operator === '-' && TRANSFER_PHONES.some(p => dest.includes(p));
  }).map(row => {
    const datetime = getCol(row, '発着信時間') || '';
    const status = getCol(row, '状態') || '';
    const talkTime = getCol(row, '通話時間') || '0';
    return {
      datetime,
      date: datetime.substring(0, 10),
      hour: parseInt(datetime.substring(11, 13)) || 0,
      answered: status === '完了' || (parseInt(talkTime) > 0 && status !== 'キャンセル'),
    };
  });
}

// --- 日別集計 ---
function processDailySummary(summaryRows, transfers, year, month) {
  if (!summaryRows) return [];
  const daysInMonth = new Date(year, month, 0).getDate();
  const results = [];

  for (let d = 1; d <= daysInMonth; d++) {
    const row = summaryRows.find(r => {
      const dayCol = getCol(r, '日');
      return dayCol && parseInt(dayCol) === d;
    });

    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    const dateObj = new Date(year, month - 1, d);
    const dow = dateObj.getDay();

    const calls = row ? parseInt(getCol(row, 'ACD着信') || '0') : 0;
    const answered = row ? parseInt(getCol(row, 'OP応答') || '0') : 0;
    const abandoned = row ? parseInt(getCol(row, '放棄') || getCol(row, '顧客切断') || '0') : 0;
    const overflow = row ? parseInt(getCol(row, '溢れ') || '0') : 0;
    const rate = calls > 0 ? Math.round((answered / calls) * 1000) / 10 : 0;

    // 転送件数（その日の分）
    const dayTransfers = transfers.filter(t => t.date === dateStr);
    const transferCount = dayTransfers.length;

    results.push({
      date: dateStr,
      day: d,
      dow,
      dowName: DOW_NAMES[dow],
      calls,
      answered,
      rate,
      rateClass: calls > 0 ? rateClass(rate) : '',
      abandoned,
      abandonRate: calls > 0 ? Math.round((abandoned / calls) * 1000) / 10 : 0,
      overflow,
      transferCount,
    });
  }

  return results;
}

// --- ACD別集計 ---
function processAcdReport(acdRows) {
  if (!acdRows) return [];
  return acdRows.map(row => {
    const id = getCol(row, 'グループ') && getCol(row, 'グループ').match(/\d+/) ? getCol(row, 'グループ').match(/\d+/)[0] : '';
    const groupId = getCol(row, '番号') || id || '';
    const name = getCol(row, '名') || ACD_NAMES[groupId] || groupId;
    const calls = parseInt(getCol(row, 'ACD着信') || '0');
    const answered = parseInt(getCol(row, 'OP応答') || '0');
    const abandoned = parseInt(getCol(row, '顧客切断') || getCol(row, '放棄') || '0');
    const overflow = parseInt(getCol(row, '溢れ') || '0');
    const rate = calls > 0 ? Math.round((answered / calls) * 1000) / 10 : 0;
    const abandonRate = calls > 0 ? Math.round((abandoned / calls) * 1000) / 10 : 0;

    // 通話時間・待ち時間
    const avgTalk = getCol(row, '通話時間平均') || getCol(row, '通話時間') || '00:00:00';
    const avgWait = getCol(row, '待ち時間平均') || getCol(row, '待ち時間') || '00:00:00';

    return {
      groupId,
      name: ACD_NAMES[groupId] || name,
      calls,
      answered,
      rate,
      rateClass: rateClass(rate),
      abandoned,
      abandonRate,
      overflow,
      avgTalkTime: avgTalk,
      avgWaitTime: avgWait,
    };
  }).filter(r => r.calls > 0 || Object.values(ACD_NAMES).includes(r.name));
}

// --- オペレーター別集計 ---
function processAgentReport(agentRows) {
  if (!agentRows) return [];
  return agentRows.map(row => {
    const name = getCol(row, '名前') || getCol(row, '名') || '';
    const loginId = getCol(row, 'ログインID') || '';
    const talkCount = parseInt(getCol(row, '通話回数') || '0');
    const acceptCount = parseInt(getCol(row, '受付回数') || '0');
    const talkTimeStr = getCol(row, '通話時間') || '00:00:00';
    const afterWorkStr = getCol(row, '後処理時間') || '00:00:00';
    const utilizationStr = getCol(row, '稼働率') || '0';

    const talkSec = timeToSec(talkTimeStr);
    const avgTalkSec = talkCount > 0 ? Math.round(talkSec / talkCount) : 0;
    const afterSec = timeToSec(afterWorkStr);
    const avgAfterSec = acceptCount > 0 ? Math.round(afterSec / acceptCount) : 0;

    return {
      loginId,
      name,
      talkCount,
      acceptCount,
      talkTimeTotal: talkTimeStr,
      avgTalkTime: secToMinSec(avgTalkSec),
      afterWorkTotal: afterWorkStr,
      avgAfterWork: secToMinSec(avgAfterSec),
      utilization: parseFloat(utilizationStr) || 0,
    };
  }).filter(r => r.name);
}

// --- 曜日別平均計算 ---
function calcDowAverage(dailyData) {
  const dowTotals = {};
  const dowCounts = {};
  for (let d = 0; d < 7; d++) {
    dowTotals[d] = 0;
    dowCounts[d] = 0;
  }
  dailyData.forEach(day => {
    if (day.calls > 0) {
      dowTotals[day.dow] += day.calls;
      dowCounts[day.dow]++;
    }
  });
  const result = {};
  for (let d = 0; d < 7; d++) {
    result[DOW_NAMES[d]] = dowCounts[d] > 0
      ? Math.round((dowTotals[d] / dowCounts[d]) * 10) / 10
      : null;
  }
  return result;
}

// --- メイン処理 ---
function main() {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth() + 1;
  const ym = `${year}-${String(month).padStart(2, '0')}`;

  // 先月
  const prevDate = new Date(year, month - 2, 1);
  const prevYear = prevDate.getFullYear();
  const prevMonth = prevDate.getMonth() + 1;
  const prevYm = `${prevYear}-${String(prevMonth).padStart(2, '0')}`;

  const dataBase = path.join(__dirname, '..', 'data');
  const curDir = path.join(dataBase, ym);
  const prevDir = path.join(dataBase, prevYm);

  console.log(`=== CSV → JSON 集計 ===`);
  console.log(`今月: ${ym} (${curDir})`);
  console.log(`先月: ${prevYm} (${prevDir})`);

  // CSVファイル読み込み
  const curAcdSummary = readCsvFile(findLatestCsv(curDir, 'acd_summary'));
  const curAcdReport = readCsvFile(findLatestCsv(curDir, 'acd_report'));
  const curCdr = readCsvFile(findLatestCsv(curDir, 'cdr'));
  const curAgentReport = readCsvFile(findLatestCsv(curDir, 'agent_report'));

  const prevAcdSummary = readCsvFile(findLatestCsv(prevDir, 'acd_summary'));
  const prevAcdReport = readCsvFile(findLatestCsv(prevDir, 'acd_report'));
  const prevCdr = readCsvFile(findLatestCsv(prevDir, 'cdr'));
  const prevAgentReport = readCsvFile(findLatestCsv(prevDir, 'agent_report'));

  console.log(`今月CSV: summary=${!!curAcdSummary} acd=${!!curAcdReport} cdr=${!!curCdr} agent=${!!curAgentReport}`);
  console.log(`先月CSV: summary=${!!prevAcdSummary} acd=${!!prevAcdReport} cdr=${!!prevCdr} agent=${!!prevAgentReport}`);

  // 転送データ抽出
  const curTransfers = extractTransfers(curCdr);
  const prevTransfers = extractTransfers(prevCdr);
  console.log(`転送件数: 今月=${curTransfers.length} 先月=${prevTransfers.length}`);

  // 日別集計
  const curDaily = processDailySummary(curAcdSummary, curTransfers, year, month);
  const prevDaily = processDailySummary(prevAcdSummary, prevTransfers, prevYear, prevMonth);

  // 今月集計値
  const curActiveDays = curDaily.filter(d => d.calls > 0).length;
  const curTotalCalls = curDaily.reduce((s, d) => s + d.calls, 0);
  const curTotalAnswered = curDaily.reduce((s, d) => s + d.answered, 0);
  const curTotalRate = curTotalCalls > 0 ? Math.round((curTotalAnswered / curTotalCalls) * 1000) / 10 : 0;
  const curDailyAvg = curActiveDays > 0 ? Math.round((curTotalCalls / curActiveDays) * 10) / 10 : 0;

  // 先月集計値
  const prevActiveDays = prevDaily.filter(d => d.calls > 0).length;
  const prevTotalCalls = prevDaily.reduce((s, d) => s + d.calls, 0);
  const prevTotalAnswered = prevDaily.reduce((s, d) => s + d.answered, 0);
  const prevTotalRate = prevTotalCalls > 0 ? Math.round((prevTotalAnswered / prevTotalCalls) * 1000) / 10 : 0;
  const prevDailyAvg = prevActiveDays > 0 ? Math.round((prevTotalCalls / prevActiveDays) * 10) / 10 : 0;

  // 転送集計
  const curTransferTotal = curTransfers.length;
  const curTransferDays = new Set(curTransfers.map(t => t.date)).size;
  const curTransferAvg = curTransferDays > 0 ? Math.round((curTransferTotal / curTransferDays) * 10) / 10 : 0;
  const curTransferAnswered = curTransfers.filter(t => t.answered).length;
  const curTransferRate = curTransferTotal > 0 ? Math.round((curTransferAnswered / curTransferTotal) * 1000) / 10 : 0;

  const prevTransferTotal = prevTransfers.length;
  const prevTransferDays = new Set(prevTransfers.map(t => t.date)).size;
  const prevTransferAvg = prevTransferDays > 0 ? Math.round((prevTransferTotal / prevTransferDays) * 10) / 10 : 0;
  const prevTransferAnswered = prevTransfers.filter(t => t.answered).length;
  const prevTransferRate = prevTransferTotal > 0 ? Math.round((prevTransferAnswered / prevTransferTotal) * 1000) / 10 : 0;

  // 昨日・今日
  const todayIdx = curDaily.findIndex(d => d.day === now.getDate());
  const yesterdayIdx = curDaily.findIndex(d => d.day === now.getDate() - 1);
  const todayData = todayIdx >= 0 ? curDaily[todayIdx] : null;
  const yesterdayData = yesterdayIdx >= 0 ? curDaily[yesterdayIdx] : null;

  // ACD別
  const curAcd = processAcdReport(curAcdReport);
  const prevAcd = processAcdReport(prevAcdReport);

  // ACD別 1日平均を追加
  curAcd.forEach(a => { a.dailyAvg = curActiveDays > 0 ? Math.round((a.calls / curActiveDays) * 10) / 10 : 0; });
  prevAcd.forEach(a => { a.dailyAvg = prevActiveDays > 0 ? Math.round((a.calls / prevActiveDays) * 10) / 10 : 0; });

  // オペレーター別
  const curAgents = processAgentReport(curAgentReport);
  const prevAgents = processAgentReport(prevAgentReport);

  // オペレーター別 1日平均
  curAgents.forEach(a => { a.dailyAvg = curActiveDays > 0 ? Math.round((a.talkCount / curActiveDays) * 10) / 10 : 0; });
  prevAgents.forEach(a => { a.dailyAvg = prevActiveDays > 0 ? Math.round((a.talkCount / prevActiveDays) * 10) / 10 : 0; });

  // 曜日別平均
  const curDowAvg = calcDowAverage(curDaily);
  const prevDowAvg = calcDowAverage(prevDaily);

  // --- JSON出力 ---
  const dashboard = {
    generated: now.toISOString(),
    currentMonth: { year, month, ym, label: `${month}月` },
    prevMonth: { year: prevYear, month: prevMonth, ym: prevYm, label: `${prevMonth}月` },

    // 昨日（前日データのみ。BlueBean自体が前日更新のため今日データは取得不可）
    yesterday: yesterdayData,

    // BB受電サマリー
    bbSummary: {
      current: { total: curTotalCalls, dailyAvg: curDailyAvg, rate: curTotalRate, activeDays: curActiveDays },
      prev: { total: prevTotalCalls, dailyAvg: prevDailyAvg, rate: prevTotalRate, activeDays: prevActiveDays },
    },

    // 転送受電サマリー
    transferSummary: {
      current: { total: curTransferTotal, dailyAvg: curTransferAvg, rate: curTransferRate },
      prev: { total: prevTransferTotal, dailyAvg: prevTransferAvg, rate: prevTransferRate },
    },

    // 日別実績
    daily: { current: curDaily.reverse(), prev: prevDaily.reverse() },

    // ACD別
    acd: { current: curAcd, prev: prevAcd },

    // ACD別 転送
    acdTransfer: {
      current: { total: curTransferTotal, dailyAvg: curTransferAvg, rate: curTransferRate },
      prev: { total: prevTransferTotal, dailyAvg: prevTransferAvg, rate: prevTransferRate },
    },

    // 曜日別平均（全体）
    dowAverage: { current: curDowAvg, prev: prevDowAvg },

    // オペレーター別
    agents: { current: curAgents, prev: prevAgents },
  };

  // 出力
  const outPath = path.join(dataBase, 'dashboard.json');
  fs.writeFileSync(outPath, JSON.stringify(dashboard, null, 2), 'utf-8');
  console.log(`\n出力: ${outPath}`);
  console.log('=== 完了 ===');
}

main();
