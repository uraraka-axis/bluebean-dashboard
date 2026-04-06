/**
 * BlueBean CSV自動取得スクリプト
 * Playwrightでログイン → 4種のCSVをダウンロード
 *
 * 対象CSV:
 *   1. ACD集計レポート (acd_report)
 *   2. ACD日別サマリー (acd_summary)
 *   3. 発着信履歴 CDR (cdr)
 *   4. オペレーターレポート (agent_report)
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

// --- 設定（環境変数 or デフォルト値） ---
const BB_URL = process.env.BB_URL || 'https://bbw3476-uraraka.softsu.com';
const BB_USER = process.env.BB_USER || 'admin';
const BB_PASS = process.env.BB_PASS || 'Uraraka2026##';

// 保存先: data/YYYY-MM/
function getDataDir() {
  const now = new Date();
  const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const dir = path.join(__dirname, '..', 'data', ym);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  return dir;
}

// 今日の日付文字列 YYYY-MM-DD
function today() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

// 今月1日 YYYY-MM-DD
function firstOfMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
}

// 先月1日 / 先月末日
function lastMonthRange() {
  const now = new Date();
  const firstThis = new Date(now.getFullYear(), now.getMonth(), 1);
  const lastDayPrev = new Date(firstThis - 1);
  const firstPrev = new Date(lastDayPrev.getFullYear(), lastDayPrev.getMonth(), 1);
  const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  return { from: fmt(firstPrev), to: fmt(lastDayPrev) };
}

// 日付入力（daterangepickerを回避してJSで直接セット）
async function setDateRange(page, startDate, endDate) {
  await page.evaluate(({ s, e }) => {
    const startEl = document.querySelector('input[name="data[QueueCdr][start_date]"]')
      || document.querySelector('#start_date')
      || document.querySelector('input[name="start_date"]');
    const endEl = document.querySelector('input[name="data[QueueCdr][end_date]"]')
      || document.querySelector('#end_date')
      || document.querySelector('input[name="end_date"]');
    if (startEl) { startEl.value = s; startEl.dispatchEvent(new Event('change', { bubbles: true })); }
    if (endEl) { endEl.value = e; endEl.dispatchEvent(new Event('change', { bubbles: true })); }
    // daterangepickerを閉じる
    document.querySelectorAll('.daterangepicker').forEach(el => el.style.display = 'none');
  }, { s: startDate, e: endDate });
  // 念のためEscで閉じる
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
}

// CDR用の日付入力（フィールド名が異なる）
async function setCdrDateRange(page, startDate, endDate) {
  await page.evaluate(({ s, e }) => {
    const startEl = document.querySelector('input[name="data[Cdr][start_date]"]')
      || document.querySelector('#start_date')
      || document.querySelector('input[name="start_date"]');
    const endEl = document.querySelector('input[name="data[Cdr][end_date]"]')
      || document.querySelector('#end_date')
      || document.querySelector('input[name="end_date"]');
    if (startEl) { startEl.value = s; startEl.dispatchEvent(new Event('change', { bubbles: true })); }
    if (endEl) { endEl.value = e; endEl.dispatchEvent(new Event('change', { bubbles: true })); }
    document.querySelectorAll('.daterangepicker').forEach(el => el.style.display = 'none');
  }, { s: startDate, e: endDate });
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
}

async function main() {
  const dataDir = getDataDir();
  const todayStr = today();
  const monthStart = firstOfMonth();
  const prev = lastMonthRange();

  console.log(`=== BlueBean CSV取得 ${todayStr} ===`);
  console.log(`今月: ${monthStart} 〜 ${todayStr}`);
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

    // --- 今月データ取得 ---
    console.log('');
    console.log('2. 今月のCSV取得中...');

    // 2a. ACD集計レポート（今月）
    console.log('  [ACD集計レポート]');
    await page.goto(`${BB_URL}/admin/queue_cdrs/index/`);
    await page.waitForLoadState('networkidle');

    // 日付範囲を設定（daterangepicker回避）
    await setDateRange(page, monthStart, todayStr);

    // 検索実行
    const searchBtn = page.locator('button:has-text("検索"), input[value="検索"], button:has-text("Search")');
    if (await searchBtn.count() > 0) {
      await searchBtn.first().click({ force: true });
      await page.waitForLoadState('networkidle');
    }

    // CSVダウンロード
    const [dl1] = await Promise.all([
      page.waitForEvent('download', { timeout: 30000 }),
      page.locator('a:has-text("CSV"), button:has-text("CSV")').first().click({ force: true }),
    ]);
    await dl1.saveAs(path.join(dataDir, `acd_report_${todayStr}.csv`));
    console.log(`    保存完了`);

    // 2b. ACD日別サマリー（今月）
    console.log('  [ACD日別サマリー]');
    await page.goto(`${BB_URL}/admin/queue_cdrs/summary`);
    await page.waitForLoadState('networkidle');

    await setDateRange(page, monthStart, todayStr);

    const searchBtn2 = page.locator('button:has-text("検索"), input[value="検索"], button:has-text("Search")');
    if (await searchBtn2.count() > 0) {
      await searchBtn2.first().click({ force: true });
      await page.waitForLoadState('networkidle');
    }

    const [dl2] = await Promise.all([
      page.waitForEvent('download', { timeout: 30000 }),
      page.locator('a:has-text("CSV"), button:has-text("CSV")').first().click({ force: true }),
    ]);
    await dl2.saveAs(path.join(dataDir, `acd_summary_${todayStr}.csv`));
    console.log(`    保存完了`);

    // 2c. CDR 発着信履歴（今月）
    console.log('  [CDR 発着信履歴]');
    await page.goto(`${BB_URL}/admin/cdr/index`);
    await page.waitForLoadState('networkidle');

    await setCdrDateRange(page, monthStart, todayStr);

    const searchBtn3 = page.locator('button:has-text("検索"), input[value="検索"], button:has-text("Search")');
    if (await searchBtn3.count() > 0) {
      await searchBtn3.first().click({ force: true });
      await page.waitForLoadState('networkidle');
    }

    const [dl3] = await Promise.all([
      page.waitForEvent('download', { timeout: 30000 }),
      page.locator('a:has-text("CSV"), button:has-text("CSV")').first().click({ force: true }),
    ]);
    await dl3.saveAs(path.join(dataDir, `cdr_${todayStr}.csv`));
    console.log(`    保存完了`);

    // 2d. オペレーターレポート（今月）
    console.log('  [オペレーターレポート]');
    await page.goto(`${BB_URL}/admin/queue_cdrs/agent_report/`);
    await page.waitForLoadState('networkidle');

    await setDateRange(page, monthStart, todayStr);

    const searchBtn4 = page.locator('button:has-text("検索"), input[value="検索"], button:has-text("Search")');
    if (await searchBtn4.count() > 0) {
      await searchBtn4.first().click({ force: true });
      await page.waitForLoadState('networkidle');
    }

    const [dl4] = await Promise.all([
      page.waitForEvent('download', { timeout: 30000 }),
      page.locator('a:has-text("CSV"), button:has-text("CSV")').first().click({ force: true }),
    ]);
    await dl4.saveAs(path.join(dataDir, `agent_report_${todayStr}.csv`));
    console.log(`    保存完了`);

    // --- 先月データ取得（月初のみ or 先月データ未取得時） ---
    const prevDir = path.join(__dirname, '..', 'data', prev.from.substring(0, 7));
    const prevAcdPath = path.join(prevDir, `acd_report_${prev.to}.csv`);

    if (!fs.existsSync(prevAcdPath)) {
      console.log('');
      console.log('3. 先月のCSV取得中...');
      if (!fs.existsSync(prevDir)) {
        fs.mkdirSync(prevDir, { recursive: true });
      }

      // 先月 ACD集計レポート
      console.log('  [ACD集計レポート - 先月]');
      await page.goto(`${BB_URL}/admin/queue_cdrs/index/`);
      await page.waitForLoadState('networkidle');
      await setDateRange(page, prev.from, prev.to);
      const sBtnP1 = page.locator('button:has-text("検索"), input[value="検索"]');
      if (await sBtnP1.count() > 0) { await sBtnP1.first().click({ force: true }); await page.waitForLoadState('networkidle'); }
      const [dlP1] = await Promise.all([
        page.waitForEvent('download', { timeout: 30000 }),
        page.locator('a:has-text("CSV"), button:has-text("CSV")').first().click({ force: true }),
      ]);
      await dlP1.saveAs(path.join(prevDir, `acd_report_${prev.to}.csv`));
      console.log(`    保存完了`);

      // 先月 ACD日別サマリー
      console.log('  [ACD日別サマリー - 先月]');
      await page.goto(`${BB_URL}/admin/queue_cdrs/summary`);
      await page.waitForLoadState('networkidle');
      await setDateRange(page, prev.from, prev.to);
      const sBtnP2 = page.locator('button:has-text("検索"), input[value="検索"]');
      if (await sBtnP2.count() > 0) { await sBtnP2.first().click({ force: true }); await page.waitForLoadState('networkidle'); }
      const [dlP2] = await Promise.all([
        page.waitForEvent('download', { timeout: 30000 }),
        page.locator('a:has-text("CSV"), button:has-text("CSV")').first().click({ force: true }),
      ]);
      await dlP2.saveAs(path.join(prevDir, `acd_summary_${prev.to}.csv`));
      console.log(`    保存完了`);

      // 先月 CDR
      console.log('  [CDR - 先月]');
      await page.goto(`${BB_URL}/admin/cdr/index`);
      await page.waitForLoadState('networkidle');
      await setCdrDateRange(page, prev.from, prev.to);
      const sBtnP3 = page.locator('button:has-text("検索"), input[value="検索"]');
      if (await sBtnP3.count() > 0) { await sBtnP3.first().click({ force: true }); await page.waitForLoadState('networkidle'); }
      const [dlP3] = await Promise.all([
        page.waitForEvent('download', { timeout: 30000 }),
        page.locator('a:has-text("CSV"), button:has-text("CSV")').first().click({ force: true }),
      ]);
      await dlP3.saveAs(path.join(prevDir, `cdr_${prev.to}.csv`));
      console.log(`    保存完了`);

      // 先月 オペレーターレポート
      console.log('  [オペレーターレポート - 先月]');
      await page.goto(`${BB_URL}/admin/queue_cdrs/agent_report/`);
      await page.waitForLoadState('networkidle');
      await setDateRange(page, prev.from, prev.to);
      const sBtnP4 = page.locator('button:has-text("検索"), input[value="検索"]');
      if (await sBtnP4.count() > 0) { await sBtnP4.first().click({ force: true }); await page.waitForLoadState('networkidle'); }
      const [dlP4] = await Promise.all([
        page.waitForEvent('download', { timeout: 30000 }),
        page.locator('a:has-text("CSV"), button:has-text("CSV")').first().click({ force: true }),
      ]);
      await dlP4.saveAs(path.join(prevDir, `agent_report_${prev.to}.csv`));
      console.log(`    保存完了`);
    } else {
      console.log('');
      console.log('3. 先月のCSVは取得済み。スキップ。');
    }

    console.log('');
    console.log('=== 完了 ===');

  } catch (err) {
    console.error('エラー発生:', err.message);
    // デバッグ用スクリーンショット
    const ssPath = path.join(dataDir, `error_${todayStr}.png`);
    await page.screenshot({ path: ssPath, fullPage: true });
    console.error(`スクリーンショット保存: ${ssPath}`);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

main();
