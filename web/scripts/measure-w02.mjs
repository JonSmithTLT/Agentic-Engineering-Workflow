import { URL } from 'node:url';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
const baseline = process.env.W02_MEASURE_BASELINE === '1';
const root = baseline
  ? path.resolve('../..', 'AEW-dashboard-w01/web')
  : process.cwd();
const port = '4213',
  out =
    process.env.W02_MEASURE_OUT ??
    'docs/w02-evidence/baseline-performance.json';
const child = spawn(
  process.execPath,
  [
    path.resolve('node_modules/vite/bin/vite.js'),
    'preview',
    '--mode',
    'demo',
    '--host',
    '127.0.0.1',
    '--port',
    port,
    '--strictPort',
  ],
  { cwd: root, stdio: 'ignore' },
);
let browser;
try {
  for (let i = 0; i < 100; i++) {
    try {
      if ((await globalThis.fetch(`http://127.0.0.1:${port}`)).ok) break;
    } catch {
      /* Wait for owned server startup. */
    }
    await new Promise((r) => globalThis.setTimeout(r, 100));
  }
  browser = await chromium.launch({
    executablePath: path.resolve(
      'artifacts/playwright/browsers/chromium-1217/chrome-linux64/chrome',
    ),
  });
  const results = [];
  for (const [fixture, route] of [
    ['F6', '/work'],
    ['F7', '/history'],
  ])
    for (let repeat = 0; repeat < 3; repeat++) {
      const context = await browser.newContext({
          viewport: { width: 1440, height: 1000 },
        }),
        page = await context.newPage(),
        requests = [],
        errors = [];
      page.on('request', (r) => {
        if (r.url().includes('/api/v1'))
          requests.push(new URL(r.url()).pathname + new URL(r.url()).search);
      });
      page.on('pageerror', (e) => errors.push(e.message));
      const start = performance.now();
      await page.goto(`http://127.0.0.1:${port}${route}?fixture=${fixture}`);
      await page.waitForFunction(
        () =>
          document.querySelectorAll('tbody tr:not(.virtual-spacer)').length >=
          20,
      );
      results.push({
        fixture,
        repeat,
        render_ms: Math.round(performance.now() - start),
        rows: await page.locator('tbody tr:not(.virtual-spacer)').count(),
        requests,
        errors,
      });
      await context.close();
    }
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(
    out,
    JSON.stringify(
      {
        source: baseline
          ? 'ab6ab9814bee2f270ef61f69246aa19aca2431a9'
          : 'candidate',
        viewport: [1440, 1000],
        samples: results,
      },
      null,
      2,
    ) + '\n',
  );
} catch (e) {
  console.error(e);
  process.exitCode = 1;
} finally {
  await browser?.close();
  child.kill();
}
