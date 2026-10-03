import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const out = process.env.W03_MEASURE_OUTPUT ?? 'output/w03-measurement';
fs.mkdirSync(out, { recursive: true });
assert(fs.existsSync('artifacts/w03-baseline/dist-demo/index.html'), 'Stage frozen W02 build before measurement');
const servers = [], logs = [], results = [];
let browser;
async function serve(port, frozen) {
  const log = fs.openSync(`${out}/${port}.log`, 'w'); logs.push(log);
  const args = ['node_modules/vite/bin/vite.js', 'preview', '--mode', 'demo', '--host', '127.0.0.1', '--port', String(port), '--strictPort'];
  if (frozen) args.push('--outDir', 'artifacts/w03-baseline/dist-demo');
  const child = spawn(process.execPath, args, { stdio: ['ignore', log, log] }); servers.push(child);
  for (let i = 0; i < 100; i++) {
    if (child.exitCode !== null) throw new Error('Measurement server exited');
    try { if ((await globalThis.fetch(`http://127.0.0.1:${port}`)).ok) return; } catch { /* Owned startup. */ }
    await new Promise((r) => globalThis.setTimeout(r, 100));
  }
  throw new Error('Measurement server startup failed');
}
try {
  await Promise.all([serve(4260, true), serve(4261, false)]);
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? path.resolve('artifacts/playwright/browsers/chromium-1217/chrome-linux64/chrome') });
  for (const sample of [
    { label: 'W02 frozen Work F6', port: 4260, route: '/work?fixture=F6', selector: 'tbody tr' },
    { label: 'W03 candidate Work F6', port: 4261, route: '/work?fixture=F6', selector: 'tbody tr' },
    { label: 'W02 frozen Knowledge F1', port: 4260, route: '/knowledge?fixture=F1', selector: '.knowledge-group tbody tr' },
    { label: 'W03 candidate Journal story', port: 4261, route: '/knowledge?fixture=F1', selector: '.journal-item' },
    { label: 'W03 candidate Journal 10000', port: 4261, route: '/knowledge?fixture=F1&journal_case=large', selector: '.journal-item' },
  ]) for (let ordinal = 0; ordinal < 2; ordinal++) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    try {
      const page = await context.newPage(), errors = [], requests = [];
      page.on('pageerror', (e) => errors.push(e.message));
      page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
      page.on('response', (r) => { if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`); });
      page.on('request', (r) => { if (r.url().includes('/api/')) requests.push(r.url()); });
      const start = Date.now();
      await page.goto(`http://127.0.0.1:${sample.port}${sample.route}`);
      await page.locator(sample.selector).first().waitFor();
      await page.locator('.header-tools').getByText('HEALTHY', { exact: true }).waitFor();
      const count = await page.locator(sample.selector).count();
      assert(count > 0 && count <= (sample.selector === '.journal-item' ? 50 : 100));
      assert.deepEqual(errors, [], 'Every measured page has strict error observation');
      results.push({ name: sample.label, ordinal, elapsed_ms: Date.now() - start, rendered_records: count, dom_nodes: await page.locator('*').count(), api_reads: requests.length, detail_prefetch: requests.some((r) => /\/entries\//.test(r)), browser_transfer_bytes: await page.evaluate(() => window.performance.getEntriesByType('resource').reduce((sum, e) => sum + (e.transferSize ?? 0), 0)) });
    } finally { await context.close(); }
  }
  fs.writeFileSync(`${out}/result.json`, JSON.stringify({ frozen_commit: '43c5a8f961ff18f9249d62c0ad7f8790f2b33eaf', results, notes: 'Local warm-toolchain samples, not a timing SLA. Journal and accepted Knowledge differ in scope; only Work F6 is a like-for-like comparison.' }, null, 2) + '\n');
  console.log(JSON.stringify(results));
} finally {
  if (browser) await browser.close();
  servers.forEach((child) => child.kill('SIGTERM'));
  logs.forEach((log) => fs.closeSync(log));
}
