/**
 * BlueBean CSV自動取得スクリプト
 * Playwrightでログイン → 4種のCSVをダウンロード
 *
 * 対象CSV:
 *   1. ACD集計レポート (acd_report)
 *   2. ACD日別サマリー (acd_summary) ← 「日別集計」モード + 月ドロップダウン
 *   3. 発着信履歴 CDR (cdr) ← daterangepicker APIで日付設定
 *   4. オペレーターレポート (agent_report)
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

// --- 設定（環境変数 or デフォルト値） ---
const BB_URL = process.env.BB_URL || 'https://bbw3476-uraraka.softsu.com';
const BB_USER = process.env.BB_USER || 'admin';
const BB_PASS = process.env.BB_PASS || 'Uraraka2026##';

// JST日時を取得（GitHub ActionsはUTCで動くため）
function jstNow() {
  const now = new Date();
  // UTC → JST (+9h)
  return new Date(now.getTime() + 9 * 60 * 60 * 1000);
}

function fmtDate(d) {
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
}

// 保存先: data/YYYY-MM/
function getDataDir() {
  const now = jstNow();
  const ym = `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, '0')}`;
  const dir = path.join(__dirname, '..', 'data', ym);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  return dir;
}

// 今日の日付文字列 YYYY-MM-DD（JST）
function today() {
  return fmtDate(jstNow());
}

// 今月1日 YYYY-MM-DD（JST）
function firstOfMonth() {
  const now = jstNow();
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, '0')}-01`;
}

// 先月1日 / 先月末日（JST）
function lastMonthRange() {
  const now = jstNow();
  const firstThis = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
  const lastDayPrev = new Date(firstThis.getTime() - 1);
  const firstPrev = new Date(Date.UTC(lastDayPrev.getUTCFullYear(), lastDayPrev.getUTCMonth(), 1));
  return { from: fmtDate(firstPrev), to: fmtDate(lastDayPrev) };
}

// --- daterangepicker API経由で日付設定 ---

// ACD系ページ用（2つの独立したsingleDatePicker）
// acd_report, agent_report で使用
async function setAcdDateRange(page, startDate, endDate) {
  await page.evaluate(({ s, e }) => {
    const $ = window.jQuery;
    const startPicker = $('#QueueCdrStartDate').data('daterangepicker');
    const endPicker = $('#QueueCdrEndDate').data('daterangepicker');

    startPicker.setStartDate(s + ' 00:00:00');
    startPicker.setEndDate(s + ' 00:00:00');
    $('#QueueCdrStartDate').val(s + ' 00:00:00');

    endPicker.setStartDate(e + ' 23:59:59');
    endPicker.setEndDate(e + ' 23:59:59');
    $('#QueueCdrEndDate').val(e + ' 23:59:59');
  }, { s: startDate, e: endDate });
  await page.waitForTimeout(200);
}

// 検索ボタンクリック
async function clickSearch(page) {
  const searchBtn = page.locator('button:has-text("検索"), input[value="検索"]');
  if (await searchBtn.count() > 0) {
    await searchBtn.first().click({ force: true });
    await page.waitForLoadState('networkidle');
  }
}

// CSVダウンロード
async function downloadCsv(page, savePath) {
  const [dl] = await Promise.all([
    page.waitForEvent('download', { timeout: 30000 }),
    page.locator('a:has-text("CSV"), button:has-text("CSV")').first().click({ force: true }),
  ]);
  await dl.saveAs(savePath);
}

// ACD系レポートのCSV取得（acd_report / agent_report）
async function fetchAcdCsv(page, url, startDate, endDate, savePath, label) {
  console.log(`  [${label}]`);
  await page.goto(`${BB_URL}${url}`);
  await page.waitForLoadState('networkidle');
  await setAcdDateRange(page, startDate, endDate);
  await clickSearch(page);
  await downloadCsv(page, savePath);
  console.log(`    保存完了: ${path.basename(savePath)}`);
}

// ACD日別サマリー取得（当月用）
// 日別集計ラジオ + 日付レンジラジオ + daterangepicker で 1日〜前日
async function fetchAcdSummaryCsvByRange(page, startDate, endDate, savePath, label) {
  console.log(`  [${label}]`);
  await page.goto(`${BB_URL}/admin/queue_cdrs/summary`);
  await page.waitForLoadState('networkidle');

  // 1. 「日別集計」ラジオボタンをクリック
  await page.evaluate(() => {
    const radios = document.querySelectorAll('input[type="radio"]');
    for (const r of radios) {
      if (r.parentElement && r.parentElement.textContent.trim().includes('日別集計')) {
        r.click();
        break;
      }
    }
  });
  await page.waitForTimeout(200);

  // 2. 「日付レンジ」ラジオ（timeType=2）をクリック → 日付入力欄を有効化
  await page.evaluate(() => {
    const radio = document.querySelector('input[name="data[QueueCdr][timeType]"][value="2"]');
    if (radio) radio.click();
  });
  await page.waitForTimeout(200);

  // 3. daterangepicker APIで日付設定（#QueueCdrStartDate / #QueueCdrEndDate）
  await setAcdDateRange(page, startDate, endDate);

  await clickSearch(page);
  await downloadCsv(page, savePath);
  console.log(`    保存完了: ${path.basename(savePath)}`);
}

// ACD日別サマリー取得（前月用）
// 日別集計ラジオ + 集計期間ラジオ（月ドロップダウン）
async function fetchAcdSummaryCsvByMonth(page, year, month, savePath, label) {
  console.log(`  [${label}]`);
  await page.goto(`${BB_URL}/admin/queue_cdrs/summary`);
  await page.waitForLoadState('networkidle');

  // 1. 「日別集計」ラジオボタンをクリック
  await page.evaluate(() => {
    const radios = document.querySelectorAll('input[type="radio"]');
    for (const r of radios) {
      if (r.parentElement && r.parentElement.textContent.trim().includes('日別集計')) {
        r.click();
        break;
      }
    }
  });
  await page.waitForTimeout(200);

  // 2. 「集計期間」ラジオ（timeType=1 月選択側）をクリック → ドロップダウンを有効化
  await page.evaluate(() => {
    const radio = document.querySelector('input[name="data[QueueCdr][timeType]"][value="1"]');
    if (radio) radio.click();
  });
  await page.waitForTimeout(300);

  // 3. 月ドロップダウンで対象月を選択（value形式: "YYYY-M" ※ゼロ埋めなし）
  const monthValue = `${year}-${month}`;
  await page.selectOption('#QueueCdrDateRange', monthValue);
  await page.waitForTimeout(200);

  await clickSearch(page);
  await downloadCsv(page, savePath);
  console.log(`    保存完了: ${path.basename(savePath)}`);
}

// CDR取得（daterangepicker APIで日付設定 → 検索 → CSVダウンロード）
async function fetchCdrCsv(page, startDate, endDate, savePath, label) {
  console.log(`  [${label}]`);
  await page.goto(`${BB_URL}/admin/cdr/index`);
  await page.waitForLoadState('networkidle');

  // daterangepicker APIで日付を設定（CDRは1つのrange picker）
  await page.evaluate(({ s, e }) => {
    const $ = window.jQuery;
    const input = $('input[name="start_date"]');
    const picker = input.data('daterangepicker');
    picker.setStartDate(s + ' 00:00:00');
    picker.setEndDate(e + ' 23:59:59');
    input.val(s + ' 00:00:00 ~ ' + e + ' 23:59:59');
  }, { s: startDate, e: endDate });
  await page.waitForTimeout(200);

  // 検索ボタンクリック
  await clickSearch(page);
  // DataTableのAJAXロード完了を待つ
  await page.waitForTimeout(2000);

  // CSVダウンロード（CDRは /admin/cdr/csv_download/ のリンク）
  const [dl] = await Promise.all([
    page.waitForEvent('download', { timeout: 30000 }),
    page.locator('a[href*="csv_download"]').first().click({ force: true }),
  ]);
  await dl.saveAs(savePath);
  console.log(`    保存完了: ${path.basename(savePath)}`);
}

async function main() {
  const dataDir = getDataDir();
  const todayStr = today();
  const monthStart = firstOfMonth();
  const prev = lastMonthRange();

  // 今月の年月
  const now = jstNow();
  const curYear = now.getUTCFullYear();
  const curMonth = now.getUTCMonth() + 1;

  // 先月の年月
  const prevYm = prev.from.substring(0, 7); // "YYYY-MM"
  const prevYear = parseInt(prevYm.split('-')[0]);
  const prevMonth = parseInt(prevYm.split('-')[1]);

  // 前日の日付（全CSV共通の終了日）
  const yesterday = new Date(Date.UTC(curYear, curMonth - 1, now.getUTCDate() - 1));
  const yesterdayStr = fmtDate(yesterday);

  // 月初1日チェック: 前日が先月 → 当月データなし
  const isFirstDay = now.getUTCDate() === 1;

  console.log(`=== BlueBean CSV取得 ${todayStr} (JST) ===`);
  if (!isFirstDay) {
    console.log(`今月: ${monthStart} 〜 ${yesterdayStr}`);
  } else {
    console.log(`今月: 月初1日のため当月取得スキップ`);
  }
  console.log(`先月: ${prev.from} 〜 ${prev.to}`);
  console.log(`保存先: ${dataDir}`);
  console.log('');

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();

  try {
    // --- ログイン ---
    console.log('1. ログイン中...');
    await page.goto(`${BB_URL}/admin_users/login`);
    await page.fill('input[name="data[AdminUser][username]"]', BB_USER);
    await page.fill('input[name="data[AdminUser][password]"]', BB_PASS);
    await page.click('button[type="submit"], input[type="submit"]');
    await page.waitForURL('**/admin/**', { timeout: 15000 });
    console.log('  ログイン成功');

    // --- 今月データ取得（月初1日はスキップ） ---
    if (!isFirstDay) {
      console.log('');
      console.log('2. 今月のCSV取得中...');

      await fetchAcdCsv(page, '/admin/queue_cdrs/index/', monthStart, yesterdayStr,
        path.join(dataDir, `acd_report_${todayStr}.csv`), 'ACD集計レポート');

      await fetchAcdSummaryCsvByRange(page, monthStart, yesterdayStr,
        path.join(dataDir, `acd_summary_${todayStr}.csv`), 'ACD日別サマリー');

      await fetchCdrCsv(page, monthStart, yesterdayStr,
        path.join(dataDir, `cdr_${todayStr}.csv`), 'CDR 発着信履歴');

      await fetchAcdCsv(page, '/admin/queue_cdrs/agent_report/', monthStart, yesterdayStr,
        path.join(dataDir, `agent_report_${todayStr}.csv`), 'オペレーターレポート');
    } else {
      console.log('');
      console.log('2. 月初1日のため当月CSV取得をスキップ');
    }

    // --- 先月データ取得（未取得時のみ） ---
    const prevDir = path.join(__dirname, '..', 'data', prevYm);
    const prevAcdPath = path.join(prevDir, `acd_report_${prev.to}.csv`);

    if (!fs.existsSync(prevAcdPath)) {
      console.log('');
      console.log('3. 先月のCSV取得中...');
      if (!fs.existsSync(prevDir)) {
        fs.mkdirSync(prevDir, { recursive: true });
      }

      await fetchAcdCsv(page, '/admin/queue_cdrs/index/', prev.from, prev.to,
        path.join(prevDir, `acd_report_${prev.to}.csv`), 'ACD集計レポート - 先月');

      // 前月サマリー: 月ドロップダウンで丸ごと取得
      await fetchAcdSummaryCsvByMonth(page, prevYear, prevMonth,
        path.join(prevDir, `acd_summary_${prev.to}.csv`), 'ACD日別サマリー - 先月');

      await fetchCdrCsv(page, prev.from, prev.to,
        path.join(prevDir, `cdr_${prev.to}.csv`), 'CDR - 先月');

      await fetchAcdCsv(page, '/admin/queue_cdrs/agent_report/', prev.from, prev.to,
        path.join(prevDir, `agent_report_${prev.to}.csv`), 'オペレーターレポート - 先月');
    } else {
      console.log('');
      console.log('3. 先月のCSVは取得済み。スキップ。');
    }

    console.log('');
    console.log('=== 完了 ===');

  } catch (err) {
    console.error('エラー発生:', err.message);
    const ssPath = path.join(dataDir, `error_${todayStr}.png`);
    await page.screenshot({ path: ssPath, fullPage: true });
    console.error(`スクリーンショット保存: ${ssPath}`);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

main();
