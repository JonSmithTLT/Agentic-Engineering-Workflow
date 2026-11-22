import { spawn } from 'node:child_process';
import fs from 'node:fs';
import { URL } from 'node:url';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const output = process.env.ACTIVITY_OUTPUT ?? 'output/playwright-activity';
fs.mkdirSync(output, { recursive: true });
const ports = { worker: process.env.ACTIVITY_WORKER_PORT ?? '4490', http: process.env.ACTIVITY_HTTP_PORT ?? '4491' };
const owned = [], results = [];
let browser;
async function start(adapter) {
  const log = fs.openSync(`${output}/${adapter}-server.log`, 'w');
  const child = spawn(process.execPath, adapter === 'http' ? ['--experimental-strip-types', 'scripts/demo-server.mjs'] : ['node_modules/vite/bin/vite.js', 'preview', '--mode', 'demo', '--host', '127.0.0.1', '--port', ports.worker, '--strictPort'], { env: { ...process.env, DASHBOARD_PORT: ports.http }, stdio: ['ignore', log, log] });
  owned.push(child);
  const base = `http://127.0.0.1:${ports[adapter]}`;
  for (let attempt = 0; attempt < 100; attempt++) {
    if (child.exitCode !== null) throw new Error('Owned Activity server exited');
    try { if ((await globalThis.fetch(base)).ok) return base; } catch { /* owned startup */ }
    await new Promise(resolve => globalThis.setTimeout(resolve, 100));
  }
  throw new Error('Activity server did not start');
}
try {
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH ?? 'artifacts/playwright/browsers/chromium-1217/chrome-linux64/chrome' });
  for (const adapter of ['worker', 'http']) {
    const base = await start(adapter);
    for (const width of [1440, 390, 720]) {
      const context = await browser.newContext({ viewport: { width, height: 900 }, serviceWorkers: adapter === 'http' ? 'block' : 'allow', permissions: ['clipboard-read', 'clipboard-write'] });
      await context.addInitScript(() => window.localStorage.setItem('aew-theme', 'light'));
      const page = await context.newPage(), errors = [], reads = [], responses = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => { if (new URL(request.url()).pathname === '/api/v1/activity') reads.push(request.url()); });
      page.on('response', response => { if (new URL(response.url()).pathname === '/api/v1/activity') responses.push(response.status()); });
      await context.tracing.start({ screenshots: true, snapshots: true });
      try {
        await page.goto(`${base}/?fixture=F7`);
        await page.getByRole('link', { name: 'View all activity', exact: true }).click();
        await page.getByRole('heading', { name: 'Activity records', exact: true }).waitFor();
        assert.equal(await page.locator('article.activity-record').count(), 50);
        assert(reads.every(url => new URL(url).searchParams.get('limit') === '50'));
        assert.equal(await page.locator('article.activity-record script').count(), 0);
        assert.equal(await page.evaluate(() => window.__activityHostile), undefined);
        await page.locator('article.activity-record').nth(1).getByText('No detail view available.', { exact: true }).waitFor();
        for (const theme of ['light', 'dark']) {
          if (width < 1024) await page.getByRole('button', { name: 'Toggle navigation', exact: true }).click();
          await page.getByRole('combobox', { name: 'Appearance' }).selectOption(theme);
          if (width < 1024) await page.getByRole('button', { name: 'Close navigation', exact: true }).click();
          assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), theme);
          await page.evaluate(() => window.scrollTo(0, 0));
          await page.screenshot({ path: `${output}/${adapter}-${width}-${theme}.png` });
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'Activity viewport stays bounded');
        }
        await page.getByRole('button', { name: 'Next page', exact: true }).click();
        await page.getByRole('heading', { name: 'Activity records', exact: true }).waitFor();
        await page.waitForFunction(() => document.querySelectorAll('article.activity-record').length === 11);
        assert.equal(await page.evaluate(() => document.activeElement?.textContent), 'Activity records');
        const heading = await page.getByRole('heading', { name: 'Activity records', exact: true }).boundingBox();
        assert(heading.y >= 0 && heading.y < 500, 'Replacement heading is visible');
        assert.equal(await page.getByText('Verification started', { exact: true }).count(), 0);
        await page.getByRole('button', { name: 'Copy dashboard link', exact: true }).click();
        await page.getByText('Dashboard link copied.', { exact: true }).waitFor();
        const copied = await page.evaluate(() => navigator.clipboard.readText());
        assert(new URL(copied).searchParams.get('cursor'));
        await page.goto(copied);
        await page.waitForFunction(() => document.querySelectorAll('article.activity-record').length === 11);
        const refreshed = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/activity');
        await page.getByRole('button', { name: 'Refresh page', exact: true }).click();
        assert.equal((await refreshed).status(), 304, 'Conditional manual refresh preserves pinned page');
        assert.equal(await page.locator('article.activity-record').count(), 11);
        await page.getByRole('button', { name: 'First page', exact: true }).click();
        await page.getByText('Verification started', { exact: true }).waitFor();
        assert.equal(await page.locator('article.activity-record').count(), 50);
        await page.goto(`${base}/activity?fixture=F7&cursor=a&cursor=b`);
        const before = reads.length;
        await page.getByText('Check the filter values. No request was sent.', { exact: true }).waitFor();
        assert.equal(reads.length, before);
        assert.deepEqual(errors, []);
        results.push({ adapter, width, result: 'PASS', rows: [50, 11, 50], statuses: responses, zoom: width === 720 ? 'narrow reflow proxy, not real browser zoom' : 'not tested' });
      } finally { await context.tracing.stop({ path: `${output}/${adapter}-${width}.zip` }); await context.close(); }
    }
  }
  fs.writeFileSync(`${output}/results.json`, JSON.stringify(results, null, 2));
  console.log('Activity compiled checks PASS', results);
} finally { await browser?.close(); for (const child of owned) child.kill(); }
