import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { URL } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
const base = process.env.DASHBOARD_PREVIEW_URL ?? 'http://127.0.0.1:4173';
const production =
  process.env.DASHBOARD_PRODUCTION_URL ?? 'http://127.0.0.1:4175';
const out = 'output/playwright-review-fixes';
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
const errors = [],
  writes = [],
  remote = [],
  checks = [],
  sequences = [];
function capture(page, origin) {
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('request', (r) => {
    if (!r.url().startsWith(origin + '/') && !r.url().startsWith('data:'))
      remote.push(r.url());
    if (r.url().includes('/api/v1/') && !['GET', 'HEAD'].includes(r.method()))
      writes.push(r.url());
  });
}
try {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  const page = await ctx.newPage();
  capture(page, base);
  await page.goto(base + '/history/T-0004?fixture=F3');
  await page
    .getByRole('heading', { name: 'Lineage and links', exact: true })
    .waitFor();
  assert.equal(await page.locator('.unknown').count(), 0);
  assert.equal(
    await page
      .getByRole('link', { name: 'INV-0001', exact: true })
      .getAttribute('href'),
    '/runs/INV-0001?fixture=F3',
  );
  assert.equal(
    await page
      .getByRole('link', { name: 'INV-0001-verification-1', exact: true })
      .getAttribute('href'),
    '/evidence/INV-0001-verification-1?fixture=F3',
  );
  const work = await page
    .getByRole('link', { name: 'Work lookup', exact: true })
    .evaluateAll((links) => links.map((a) => a.getAttribute('href')));
  const history = await page
    .getByRole('link', { name: 'History lookup', exact: true })
    .evaluateAll((links) => links.map((a) => a.getAttribute('href')));
  for (const id of ['T-0002', 'S-0001', 'T-0003']) {
    assert(work.includes(`/work/${id}?fixture=F3`));
    assert(history.includes(`/history/${id}?fixture=F3`));
  }
  assert.equal(
    await page
      .getByText('TOKEN-0001', { exact: true })
      .evaluate((el) => el.closest('a')),
    null,
  );
  assert.equal(
    await page
      .getByText('a'.repeat(40), { exact: true })
      .evaluate((el) => el.closest('a')),
    null,
  );
  await page.screenshot({
    path: `${out}/history-relations-light.png`,
    fullPage: true,
  });
  await page.getByRole('link', { name: 'INV-0001', exact: true }).click();
  await page
    .getByRole('heading', { name: 'Harness runs', exact: true })
    .waitFor();
  await page.goto(base + '/history/T-0004?fixture=F3');
  await page
    .getByRole('link', { name: 'INV-0001-verification-1', exact: true })
    .click();
  await page
    .getByRole('heading', { name: 'Evidence body', exact: true })
    .waitFor();
  checks.push(
    'FR-1: all seven known History link types recognized; correct destination navigation; tokens/commits plain',
  );
  await ctx.close();
  for (const stuck of [false, true]) {
    const c = await browser.newContext({
      serviceWorkers: 'block',
      viewport: { width: 1440, height: 1000 },
    });
    const p = await c.newPage();
    capture(p, production);
    const f1 = JSON.parse(
      fs.readFileSync('src/api/mock/fixtures/F1.json', 'utf8'),
    );
    let current = 42,
      projectRequests = 0;
    const served = [];
    await c.route('**/api/v1/**', async (route) => {
      const req = route.request(),
        url = new URL(req.url());
      const key = url.pathname.slice('/api/v1'.length);
      const body = JSON.parse(JSON.stringify(f1.responses[key]));
      assert(body, 'Unknown route ' + key);
      if (key === '/project') projectRequests++;
      body.control_revision = String(
        stuck && key === '/project' ? 42 : current,
      );
      const etag =
        '"' +
        createHash('sha256')
          .update(JSON.stringify([url.pathname, url.search, body]))
          .digest('hex') +
        '"';
      served.push({
        route: key,
        revision: body.control_revision,
        conditional: req.headers()['if-none-match'] === etag,
      });
      if (req.headers()['if-none-match'] === etag)
        await route.fulfill({ status: 304, headers: { ETag: etag } });
      else await route.fulfill({ json: body, headers: { ETag: etag } });
    });
    await p.clock.install();
    await p.goto(production + '/work/T-0001');
    await p.clock.runFor(200);
    await p
      .getByRole('heading', {
        name: 'Validate projection consistency',
        exact: true,
      })
      .waitFor();
    for (let i = 0; i < 20; i++) {
      current++;
      await p.clock.runFor(3000);
      // Virtual time advances faster than network/React IPC. Drain that work
      // before the next backend revision, so the probe tests actual round trips.
      for (let drain = 0; drain < 3; drain++) {
        await delay(10);
        await p.clock.runFor(10);
      }
      if (!stuck) {
        for (
          let drain = 0;
          drain < 25 &&
          (await p.getByText('CURRENT', { exact: true }).count()) === 0;
          drain++
        ) {
          await delay(10);
          await p.clock.runFor(10);
        }
      }
      if (!stuck)
        assert.equal(await p.getByText(/Mixed revisions persist/).count(), 0);
    }
    if (stuck) await p.getByText(/Mixed revisions persist/).waitFor();
    else {
      assert.equal(await p.getByText('CURRENT', { exact: true }).count(), 1);
      assert(projectRequests > 10);
    }
    assert(projectRequests < 40, 'Unbounded project catch-up requests');
    sequences.push({
      scenario: stuck ? 'stuck project with conditional 304' : 'busy healthy',
      simulated_seconds_at_least: 60,
      revision_advances: 20,
      project_requests: projectRequests,
    });
    await p.screenshot({
      path: `${out}/${stuck ? 'persistent-divergence' : 'busy-current'}.png`,
      fullPage: true,
    });
    checks.push(
      stuck
        ? 'FR-2: persistent old 304 projection still warns; catch-up stays bounded'
        : 'FR-2: 60 simulated seconds of busy revisions catch older views up without persistent warning',
    );
    await c.close();
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(remote, []);
  assert.deepEqual(writes, []);
  checks.push('No browser/CSP errors, remote resources or API writes');
  fs.writeFileSync(
    `${out}/browser-review-fixes.json`,
    JSON.stringify(
      {
        status: 'PASS',
        playwright: '1.59.1',
        chromium_revision: revision,
        browser_version: browser.version(),
        checks,
        sequences,
        errors,
        remote,
        writes,
        scope:
          'Compiled FR-1 and FR-2 regression; synthetic conditional API and simulated browser time, not live Engine',
      },
      null,
      2,
    ) + '\n',
  );
  console.log(`PASS ${checks.length} review-fix checks`);
} finally {
  await browser.close();
}
