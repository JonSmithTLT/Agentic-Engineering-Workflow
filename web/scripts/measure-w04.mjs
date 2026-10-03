import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
const out = process.env.W04_MEASURE_OUTPUT ?? 'output/w04-measurements';
fs.mkdirSync(out, { recursive: true });
const baseline = path.resolve('artifacts/w04-baseline/source/web'), compiled = path.resolve('artifacts/w04-baseline/dist-demo');
const children = [], samples = [];
let browser;
async function start(port, cwd, root) {
  const log = fs.openSync(`${out}/server-${port}.log`, 'w');
  const child = spawn(process.execPath, ['--experimental-strip-types', 'scripts/demo-server.mjs'], { cwd, env: { ...process.env, DASHBOARD_PORT: String(port), ...(root ? { DASHBOARD_STATIC_ROOT: root } : {}) }, stdio: ['ignore', log, log] }); children.push(child);
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 100; i++) { if (child.exitCode !== null) throw new Error('Measurement server exited'); try { if ((await globalThis.fetch(base)).ok) return base; } catch { /* Startup */ } await new Promise(r => globalThis.setTimeout(r, 100)); }
  throw new Error('Measurement server startup failed');
}
try {
  const [oldBase, newBase] = await Promise.all([start(4270, baseline, compiled), start(4271, process.cwd())]);
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? path.resolve('artifacts/playwright/browsers/chromium-1217/chrome-linux64/chrome') });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, serviceWorkers: 'block' });
  for (const [label, base, route, selector, population] of [['W03 baseline', oldBase, '/knowledge?fixture=F1&journal_case=large', '.journal-item', 10000], ['W04 source chooser', newBase, '/compare?fixture=F1&investigation_case=large&choose=a', '.source-chooser tbody tr', 1003]]) {
    for (let i = 0; i < 3; i++) {
      const page = await context.newPage(), requests = [], errors = [], bodies = [];
      page.on('request', r => { if (r.url().includes('/api/')) requests.push(r.url()); });
      page.on('pageerror', e => errors.push(e.message)); page.on('response', r => { if (r.url().includes('/api/')) bodies.push(r.body().then(body => body.length)); });
      const started = Date.now(); await page.goto(base + route); await page.locator(selector).first().waitFor();
      assert.equal(await page.locator(selector).count(), 50); assert.deepEqual(errors, []);
      const sample = { label, dataset_population: population, sample: i, warmup: i === 0, render_ready_ms: Date.now() - started, rows: 50, dom_nodes: await page.locator('*').count(), api_requests: requests.length, api_response_bytes: (await Promise.all(bodies)).reduce((a, b) => a + b, 0) };
      const first = await page.locator(selector).first().textContent();
      await page.getByRole('button', { name: 'Next page', exact: true }).click(); await page.waitForURL(/cursor=/);
      await page.waitForFunction(({ selector, first }) => { const rows = document.querySelectorAll(selector); return rows.length === 50 && rows[0].textContent !== first; }, { selector, first });
      assert.equal(await page.locator(selector).count(), 50); await Promise.all(bodies);
      sample.rows_after_paging = await page.locator(selector).count(); samples.push(sample); await page.close();
    }
  }
  await context.close();
  fs.writeFileSync(`${out}/result.json`, JSON.stringify({ baseline_commit: '86d301b5dc848de095028470b6efcc3b515c420c', samples, caveat: 'One warmup and two warm samples per surface; different datasets and workflows. These establish bounded rendering/requests, not a speed improvement or SLA. CHROMIUM_PATH override used when supplied.' }, null, 2) + '\n');
  console.log(JSON.stringify(samples));
} finally { await browser?.close(); for (const child of children) child.kill('SIGTERM'); }
