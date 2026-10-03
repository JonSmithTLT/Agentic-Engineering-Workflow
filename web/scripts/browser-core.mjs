import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const base = process.env.DASHBOARD_PREVIEW_URL ?? 'http://127.0.0.1:4173';
const production =
  process.env.DASHBOARD_PRODUCTION_URL ?? 'http://127.0.0.1:4175';
const out = 'output/playwright-core';
fs.mkdirSync(out, { recursive: true });
const manifest = JSON.parse(
  fs.readFileSync('node_modules/playwright-core/browsers.json', 'utf8'),
);
const revision = manifest.browsers.find((x) => x.name === 'chromium').revision;
const browser = await chromium.launch({
  executablePath: path.resolve(
    `artifacts/playwright/browsers/chromium-${revision}/chrome-linux64/chrome`,
  ),
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
});
const page = await context.newPage();
const errors = [],
  writes = [],
  remote = [],
  checks = [];
const capture = (target, origin) => {
  target.on('pageerror', (e) => errors.push(e.message));
  target.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  target.on('request', (r) => {
    if (!r.url().startsWith(origin + '/') && !r.url().startsWith('data:'))
      remote.push(r.url());
    if (r.url().includes('/api/v1/') && !['GET', 'HEAD'].includes(r.method()))
      writes.push(r.url());
  });
};
capture(page, base);
const api = [];
page.on('request', (r) => {
  if (r.url().includes('/api/v1/')) api.push(r.url());
});
async function visit(route, heading, fixture = 'F1') {
  await page.goto(
    `${base}${route}${route.includes('?') ? '&' : '?'}fixture=${fixture}`,
  );
  await page
    .getByRole('heading', { name: heading, exact: true })
    .first()
    .waitFor();
}
try {
  await visit('/runs', 'Runs records');
  assert.equal(
    await page.getByText('No harness runs supplied', { exact: true }).count(),
    1,
  );
  await page.getByRole('link', { name: 'INV-0001', exact: true }).click();
  await page
    .getByRole('heading', { name: 'Harness runs', exact: true })
    .waitFor();
  await page.reload();
  await page.getByText('R-INV-0001-1', { exact: true }).waitFor();
  await page.screenshot({ path: `${out}/run-light.png` });
  checks.push(
    'Runs includes no-harness invocations, nested harness inspection and detail reload',
  );

  await visit('/evidence?work=T-0001', 'Evidence records');
  assert(api.some((url) => url.includes('/evidence?limit=100&work=T-0001')));
  await page
    .getByRole('link', { name: 'INV-0001-verification-1', exact: true })
    .click();
  await page
    .getByRole('heading', { name: 'Evidence body', exact: true })
    .waitFor();
  await page.getByText('Evaluated snapshot and plan bindings').click();
  await page.getByText(/git-tree:32381523/).waitFor();
  await page.reload();
  await page
    .getByRole('heading', { name: 'Evidence body', exact: true })
    .waitFor();
  await page.getByLabel('Appearance').selectOption('dark');
  await page.screenshot({ path: `${out}/evidence-dark.png` });
  checks.push(
    'Evidence backend work filter, provenance/bindings, safe JSON and deep-link reload',
  );

  await visit('/knowledge', 'Knowledge records');
  await page
    .getByRole('link', {
      name: 'Keep dashboard inspection read-only',
      exact: true,
    })
    .click();
  await page
    .getByRole('heading', {
      name: 'Keep dashboard inspection read-only',
      exact: true,
    })
    .waitFor();
  await page.reload();
  await page
    .getByRole('link', { name: 'Contract checks', exact: true })
    .waitFor();
  await page.screenshot({ path: `${out}/knowledge-dark.png` });
  checks.push(
    'Knowledge page grouping, decision details, provenance and deep-link reload',
  );

  await visit('/history', 'History records', 'F3');
  const start = api.length;
  await page.getByRole('link', { name: 'T-0004', exact: true }).click();
  await page.getByText('AN-0002', { exact: true }).waitFor();
  await page.reload();
  await page.getByText('AN-0001', { exact: true }).waitFor();
  await page.getByText('Content SHA-256', { exact: true }).waitFor();
  assert.equal(
    await page.getByText(/Archived records are never current evidence/).count(),
    1,
  );
  assert(api.slice(start).some((url) => url.includes('annotations_limit=100')));
  await page.screenshot({ path: `${out}/history-detail-dark.png` });
  checks.push(
    'Manifest/trust/hash details, lineage, annotation list and bounded annotation request after reload',
  );

  await visit('/history', 'History records', 'F7');
  await page.getByRole('link', { name: 'T-H000100', exact: true }).waitFor();
  assert.equal(
    await page.getByRole('link', { name: 'T-H000101', exact: true }).count(),
    0,
  );
  await page.getByRole('button', { name: 'Next page', exact: true }).click();
  await page.getByRole('link', { name: 'T-H000101', exact: true }).waitFor();
  await page.getByRole('link', { name: 'T-H000101', exact: true }).click();
  await page.getByText('Manifest sequence 101', { exact: false }).waitFor();
  await page.reload();
  await page.getByText('Manifest sequence 101', { exact: false }).waitFor();
  checks.push(
    '50000-record History fixture stays bounded; cursor page and generated deep detail reload',
  );

  await visit('/attention', 'Attention records');
  await page
    .getByRole('heading', { name: 'Disposition required', exact: true })
    .waitFor();
  await page.getByText('Backend reasons', { exact: true }).click();
  await page.getByText('BACKEND_EXPLANATION', { exact: true }).waitFor();
  await page.screenshot({ path: `${out}/attention-dark.png` });
  checks.push(
    'Attention displays backend decision/reasons and subject links without action controls',
  );

  const suppressedStart = api.length;
  await visit('/history', 'Data unavailable', 'F9');
  await visit('/attention', 'Data unavailable', 'F9');
  await visit('/queue', 'Data unavailable', 'F9');
  assert(
    !api
      .slice(suppressedStart)
      .some((url) =>
        /\/api\/v1\/(history|attention|queue)(?:[/?]|$)/.test(url),
      ),
  );
  checks.push(
    'Downgraded History/Attention and Queue suppress requests and explain unavailable capabilities',
  );

  await page.setViewportSize({ width: 390, height: 844 });
  for (const [route, heading] of [
    ['/runs', 'Runs records'],
    ['/evidence', 'Evidence records'],
    ['/knowledge', 'Knowledge records'],
    ['/history', 'History records'],
    ['/attention', 'Attention records'],
  ]) {
    await visit(route, heading);
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
      route + ' overflows viewport',
    );
  }
  await page.screenshot({ path: `${out}/attention-phone.png` });
  await visit('/evidence/INV-0001-verification-1', 'Evidence body');
  await page.getByText('Evaluated snapshot and plan bindings').click();
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  );
  await page.screenshot({ path: `${out}/evidence-phone.png` });
  checks.push(
    'All core collection pages and expanded Evidence bindings fit phone viewport with panel-only table overflow',
  );
  await page.setViewportSize({ width: 1440, height: 1000 });
  await visit('/runs', 'Runs records');
  await page.keyboard.press('Tab');
  assert.equal(
    await page.evaluate(() => document.activeElement?.textContent),
    'Skip to content',
  );
  await page.keyboard.press('Enter');
  assert.equal(
    await page.evaluate(() => document.activeElement?.id),
    'content',
  );
  await page.getByLabel('Appearance').selectOption('light');
  await page.screenshot({ path: `${out}/runs-light.png` });
  checks.push(
    'Keyboard skip link and theme control remain functional on expanded core routes',
  );

  const prodContext = await browser.newContext({
    serviceWorkers: 'block',
    viewport: { width: 1440, height: 1000 },
  });
  const prod = await prodContext.newPage();
  capture(prod, production);
  for (const [route, heading] of [
    ['/runs', 'Runs records'],
    ['/runs/INV-0001', 'Harness runs'],
    ['/evidence', 'Evidence records'],
    ['/evidence/INV-0001-verification-1', 'Evidence body'],
    ['/knowledge', 'Knowledge records'],
    ['/knowledge/D-0001', 'Keep dashboard inspection read-only'],
    ['/history', 'History records'],
    ['/history/T-0004', 'Annotations'],
    ['/attention', 'Attention records'],
    ['/queue', 'Queue'],
  ]) {
    await prod.goto(production + route);
    await prod.getByRole('heading', { name: heading, exact: true }).waitFor();
    assert.equal(await prod.getByText('Demo data', { exact: true }).count(), 0);
  }
  assert.equal(
    await prod.evaluate(
      async () => (await navigator.serviceWorker.getRegistrations()).length,
    ),
    0,
  );
  checks.push(
    'Normal production serves every core route through fixture-backed same-origin API with no demo controls or workers',
  );
  const f4 = JSON.parse(
    fs.readFileSync('src/api/mock/fixtures/F4.json', 'utf8'),
  );
  const caps = f4.responses['/capabilities'];
  caps.data.integrity = { state: 'AVAILABLE', reasons: [] };
  await prodContext.route('**/api/v1/capabilities', (route) =>
    route.fulfill({ json: caps }),
  );
  await prodContext.route('**/api/v1/history/integrity', (route) =>
    route.fulfill({ json: f4.provisional_responses['/history/integrity'] }),
  );
  await prod.goto(production + '/history');
  await prod.getByText('CORRUPTION_REPORTED', { exact: true }).waitFor();
  await prod.getByText('Oldest unverified record', { exact: true }).waitFor();
  await prod.getByText('2026-10-02T11:30:00Z', { exact: true }).waitFor();
  await prod.screenshot({ path: `${out}/integrity-synthetic-light.png` });
  checks.push(
    'Synthetic AVAILABLE integrity: structured current/verified/full roots, backend backlog/reasons, no inferred audit status',
  );
  await prodContext.close();
  assert.deepEqual(errors, []);
  assert.deepEqual(remote, []);
  assert.deepEqual(writes, []);
  checks.push(
    'No console/page errors, CSP errors, remote subresources or API mutations',
  );
  fs.writeFileSync(
    `${out}/browser-core.json`,
    JSON.stringify(
      {
        status: 'PASS',
        playwright: '1.59.1',
        chromium_revision: revision,
        browser_version: browser.version(),
        checks,
        errors,
        remote,
        writes,
        scope:
          'D2-D4 focused compiled checks; fixture-backed adapter and explicit synthetic integrity response, not live Engine acceptance',
      },
      null,
      2,
    ) + '\n',
  );
  console.log(`PASS ${checks.length} core checks`);
} finally {
  await browser.close();
}
