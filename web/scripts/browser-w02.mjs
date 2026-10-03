import { spawn } from 'node:child_process';
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { URL } from 'node:url';
const out = process.env.W02_BROWSER_OUTPUT ?? 'output/playwright-w02',
  port = process.env.W02_DEMO_PORT ?? '4214',
  base = `http://127.0.0.1:${port}`,
  productionPort = process.env.W02_PRODUCTION_PORT ?? '4215',
  production = `http://127.0.0.1:${productionPort}`;
fs.mkdirSync(out, { recursive: true });
const owned = [];
function server(args, file, env = {}) {
  const log = fs.openSync(out + '/' + file, 'w'),
    child = spawn(process.execPath, args, {
      env: { ...process.env, ...env },
      stdio: ['ignore', log, log],
    });
  owned.push(child);
  return child;
}
async function ready(url, child) {
  for (let i = 0; i < 100; i++) {
    if (child.exitCode !== null) throw new Error('Server exited');
    try {
      if ((await globalThis.fetch(url)).ok) return;
    } catch {
      /* Wait for owned startup. */
    }
    await new Promise((r) => globalThis.setTimeout(r, 100));
  }
  throw new Error('Server did not start');
}
let browser,
  context,
  current = 'startup';
const checks = [],
  errors = [],
  responses = [],
  requests = [],
  allowedFailures = [];
async function check(name, fn) {
  current = name;
  await fn();
  checks.push({ name, result: 'PASS' });
  console.log('PASS ' + name);
}
try {
  const demo = server(
    [
      'node_modules/vite/bin/vite.js',
      'preview',
      '--mode',
      'demo',
      '--host',
      '127.0.0.1',
      '--port',
      port,
      '--strictPort',
    ],
    'demo-server.log',
  );
  const prod = server(
    ['scripts/projection-server.mjs'],
    'production-server.log',
    { DASHBOARD_PORT: productionPort },
  );
  await Promise.all([ready(base, demo), ready(production, prod)]);
  browser = await chromium.launch({
    executablePath: path.resolve(
      'artifacts/playwright/browsers/chromium-1217/chrome-linux64/chrome',
    ),
  });
  context = await browser.newContext({
    viewport: { width: 1600, height: 1000 },
    permissions: ['clipboard-read', 'clipboard-write'],
  });
  await context.tracing.start({
    screenshots: true,
    snapshots: true,
    sources: true,
  });
  const page = await context.newPage();
  page.on('pageerror', (e) =>
    errors.push({ scenario: current, message: e.message }),
  );
  page.on('console', (m) => {
    if (m.type() === 'error') {
      const expected = allowedFailures.some(
        (f) =>
          f.scenario === current &&
          m.location().url === f.url &&
          /Failed to load resource/.test(m.text()),
      );
      if (!expected)
        errors.push({
          scenario: current,
          message: m.text(),
          location: m.location(),
        });
    }
  });
  page.on('response', (r) => {
    if (r.status() >= 400)
      responses.push({
        scenario: current,
        url: r.url(),
        status: r.status(),
        expected: allowedFailures.some(
          (f) =>
            f.scenario === current &&
            f.url === r.url() &&
            f.status === r.status(),
        ),
      });
  });
  page.on('request', (r) =>
    requests.push({ scenario: current, url: r.url(), method: r.method() }),
  );
  const shot = async (name) =>
    page.screenshot({ path: out + '/' + name + '.png', fullPage: true });
  await check(
    'Work workspace preserves results while Why uses no extra reads',
    async () => {
      await page.goto(base + '/work?fixture=F1&selected=T-0001');
      await page.getByRole('button', { name: /Why state:/ }).waitFor();
      const before = requests.filter((r) => r.url.includes('/api/v1')).length;
      await page.getByRole('button', { name: /Why state:/ }).click();
      await page.getByRole('heading', { name: 'Inspect T-0001' }).waitFor();
      assert.equal(
        requests.filter((r) => r.url.includes('/api/v1')).length,
        before,
      );
      assert(
        await page
          .getByText(
            'Reasons supplied for this record; no explicit binding to this status.',
          )
          .isVisible(),
      );
      const source = page
          .locator('.inspector-panel')
          .getByRole('region', { name: 'Source provenance' }),
        observed = page
          .locator('.inspector-panel')
          .getByRole('region', { name: 'Browser observations' });
      assert(!(await source.innerText()).includes('Last checked'));
      assert((await observed.innerText()).includes('Last checked'));
      await shot('work-why-light');
      await page.getByLabel('Appearance').selectOption('dark');
      await shot('work-why-dark');
      await page.getByLabel('Appearance').selectOption('light');
      await page.getByRole('button', { name: 'Close inspector' }).click();
      assert(
        await page
          .getByRole('region', { name: 'Investigation results' })
          .isVisible(),
      );
      await page.goBack();
      await page.getByRole('heading', { name: 'Inspect T-0001' }).waitFor();
    },
  );
  await check(
    'Bounded supplied graph, edge sources, list switch and fit pan',
    async () => {
      await page.getByRole('tab', { name: 'Relations', exact: true }).click();
      await page
        .getByRole('button', { name: 'Expand T-0001', exact: true })
        .click();
      await page.locator('.provenance-node').nth(1).waitFor();
      const canvas = page.getByLabel('Provenance graph canvas');
      await page
        .getByRole('button', { name: 'Fit to width', exact: true })
        .click();
      const before = await page
          .locator('.provenance-plane')
          .evaluate((e) => e.style.transform),
        bounds = await canvas.boundingBox();
      await page.mouse.move(bounds.x + 8, bounds.y + 8);
      await page.mouse.down();
      await page.mouse.move(bounds.x + 75, bounds.y + 28, { steps: 8 });
      await page.mouse.up();
      assert.notEqual(
        await page
          .locator('.provenance-plane')
          .evaluate((e) => e.style.transform),
        before,
      );
      await page.locator('.graph-edge-list button').first().click();
      await page
        .getByRole('heading', { name: 'Supplied edge source' })
        .waitFor();
      await shot('work-relations');
      const count = await page.locator('.provenance-node').count();
      await page.getByRole('button', { name: 'Show relation list' }).click();
      await page.getByRole('button', { name: 'Show graph' }).click();
      assert.equal(await page.locator('.provenance-node').count(), count);
      await page.getByRole('button', { name: 'Close inspector' }).click();
      await page
        .getByRole('button', { name: 'Inspect relations', exact: true })
        .click();
      assert.equal(await page.locator('.provenance-node').count(), count);
    },
  );
  await check('Runs pilot, legacy routes and copied URL reload', async () => {
    await page.goto(base + '/runs?fixture=F1&selected=INV-0001');
    await page.getByRole('heading', { name: 'Invocation context' }).waitFor();
    await page.getByRole('button', { name: /Why status:/ }).click();
    await shot('runs-why');
    await page
      .locator('.inspector-panel')
      .getByRole('button', { name: 'Copy dashboard link' })
      .click();
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    assert(new URL(copied).searchParams.get('selected') === 'INV-0001');
    await page.goto(copied);
    await page.getByRole('heading', { name: 'Inspect INV-0001' }).waitFor();
    await page.goto(base + '/runs/INV-0001?fixture=F1');
    await page.getByRole('heading', { name: 'Invocation context' }).waitFor();
  });
  await check(
    'Modal inspector keyboard focus, Escape and phone overflow',
    async () => {
      await page.setViewportSize({ width: 1200, height: 900 });
      await page.goto(base + '/work?fixture=F1&selected=T-0001');
      const trigger = page.getByRole('button', { name: /Why state:/ });
      await trigger.click();
      const dialog = page.getByRole('dialog', {
        name: 'Investigation inspector',
      });
      await dialog.waitFor();
      assert(
        await page
          .getByRole('heading', { name: 'Inspect T-0001' })
          .evaluate((e) => e === document.activeElement),
      );
      await page.getByRole('tab', { name: 'Why', exact: true }).focus();
      await page.keyboard.press('ArrowRight');
      await page.waitForFunction(
        () =>
          document
            .querySelector('dialog [data-tab="relations"]')
            ?.getAttribute('aria-selected') === 'true',
      );
      await page.keyboard.press('Escape');
      await dialog.waitFor({ state: 'hidden' });
      assert(await trigger.evaluate((e) => e === document.activeElement));
      await page.setViewportSize({ width: 390, height: 844 });
      await page.getByRole('button', { name: 'Results', exact: true }).click();
      assert(
        await page
          .getByRole('region', { name: 'Investigation results' })
          .isVisible(),
      );
      await page.getByRole('button', { name: 'Detail', exact: true }).click();
      await trigger.click();
      await page
        .getByRole('dialog', { name: 'Investigation inspector' })
        .waitFor();
      await shot('work-phone-inspector');
      assert(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      );
      await page.keyboard.press('Escape');
    },
  );
  await check(
    'Concealed phone detail stops polling; revealing immediately revalidates',
    async () => {
      await page.goto(base + '/work?fixture=F1&selected=T-0001');
      await page.getByRole('button', { name: /Why state:/ }).waitFor();
      await page.getByRole('button', { name: 'Results', exact: true }).click();
      const detailCount = () =>
        requests.filter(
          (r) => new URL(r.url).pathname === '/api/v1/work/T-0001',
        ).length;
      const before = detailCount();
      await page.waitForTimeout(10500);
      assert.equal(detailCount(), before);
      await page.getByRole('button', { name: 'Detail', exact: true }).click();
      await page.waitForFunction(() =>
        document.querySelector('.investigation-detail:not([hidden])'),
      );
      await page.waitForTimeout(200);
      assert(detailCount() > before);
    },
  );
  await check(
    'Malformed IDs and unsupported history do not fall back to current reads',
    async () => {
      await page.setViewportSize({ width: 1600, height: 1000 });
      await page.goto(base + '/work?fixture=F1&selected=%3Cbad%3E');
      await page.getByText(/Locally malformed identifier/).waitFor();
      await page.goto(base + '/work?fixture=F1&selected=T-0001&rev=41');
      await page.getByText(/Historical snapshot reads/).waitFor();
      assert(
        !requests
          .filter((r) => r.scenario === current)
          .some((r) => new URL(r.url).pathname.startsWith('/api/v1/work')),
      );
      allowedFailures.push({
        scenario: current,
        url: base + '/api/v1/work/FutureNamespace-009',
        status: 404,
      });
      await page.goto(base + '/work?fixture=F1&selected=FutureNamespace-009');
      await page.getByText('Not found (404)', { exact: true }).waitFor();
      assert(
        requests.some(
          (r) => r.url === base + '/api/v1/work/FutureNamespace-009',
        ),
      );
    },
  );
  await check(
    'History provenance routes and unsupported historical claims stay explicit',
    async () => {
      await page.goto(base + '/history/T-0004?fixture=F3');
      await page
        .getByRole('button', { name: 'Inspect relations', exact: true })
        .click();
      await page
        .locator('.inspector-panel')
        .getByRole('button', { name: 'Expand T-0004' })
        .click();
      await page.locator('.inspector-panel .provenance-node').nth(1).waitFor();
      assert(
        await page
          .getByText(/current projections, not historical snapshots/)
          .first()
          .isVisible(),
      );
      await shot('history-relations');
    },
  );
  await check(
    'History moved-to hot parent resolves through Work and opens its workspace',
    async () => {
      await page.goto(base + '/history/T-0004?fixture=F3');
      await page
        .getByRole('button', { name: 'Inspect relations', exact: true })
        .click();
      const panel = page.locator('.inspector-panel');
      await panel.getByRole('button', { name: 'Expand T-0004' }).click();
      const parent = panel
        .locator('.provenance-node')
        .filter({
          has: page.getByRole('link', { name: 'S-0001', exact: true }),
        });
      await parent.getByRole('button', { name: 'Expand S-0001' }).click();
      await parent.getByText(/work · loaded revision/).waitFor();
      assert(
        requests.some(
          (r) =>
            r.scenario === current && r.url === base + '/api/v1/work/S-0001',
        ),
      );
      assert(
        !requests.some(
          (r) =>
            r.scenario === current &&
            r.url.startsWith(base + '/api/v1/history/S-0001'),
        ),
      );
      const link = parent.getByRole('link', { name: 'S-0001', exact: true });
      assert.equal(
        await link.getAttribute('href'),
        '/work?fixture=F3&selected=S-0001',
      );
      await link.click();
      await page
        .getByRole('region', { name: 'Investigation results' })
        .waitFor();
      assert.equal(new URL(page.url()).pathname, '/work');
      assert.equal(new URL(page.url()).searchParams.get('selected'), 'S-0001');
      await shot('history-hot-parent-workspace');
    },
  );
  await check(
    'CSP hostile content, clipboard failure and dataset-switch cleanup',
    async () => {
      await page.goto(base + '/work?fixture=F8&selected=T-0001');
      await page.getByRole('button', { name: /Why state:/ }).waitFor();
      assert.equal(
        await page.locator('main img, main script, main iframe').count(),
        0,
      );
      await page.evaluate(() => {
        Object.defineProperty(navigator, 'clipboard', {
          configurable: true,
          value: { writeText: () => Promise.reject(new Error('blocked')) },
        });
      });
      await page
        .locator('.workspace-controls')
        .getByRole('button', { name: 'Copy dashboard link' })
        .click();
      await page.getByLabel('Dashboard link', { exact: true }).waitFor();
      await page
        .getByRole('button', { name: 'Inspect relations', exact: true })
        .click();
      await page
        .getByRole('button', { name: 'Expand T-0001', exact: true })
        .click();
      await page.getByLabel('Demo scenario').selectOption('F1');
      await page.getByRole('heading', { name: 'Inspect T-0001' }).waitFor();
      assert.equal(await page.locator('.provenance-node').count(), 1);
    },
  );
  await check(
    'Production access refusal removes cached detail and its inspector',
    async () => {
      await page.goto(production + '/work?selected=T-0001');
      await page.getByRole('button', { name: /Why state:/ }).waitFor();
      await page.getByRole('button', { name: /Why state:/ }).click();
      await page.getByRole('heading', { name: 'Inspect T-0001' }).waitFor();
      allowedFailures.push({
        scenario: current,
        url: production + '/api/v1/work/T-0001',
        status: 403,
      });
      await page.route(production + '/api/v1/work/T-0001', (route) =>
        route.fulfill({
          status: 403,
          contentType: 'application/json',
          body: '{"code":"unavailable","message":"Access unavailable","reasons":[]}',
        }),
      );
      await page.evaluate(() =>
        window.dispatchEvent(new window.Event('focus')),
      );
      await page
        .getByText('Access unavailable (403)', { exact: true })
        .waitFor();
      assert.equal(
        await page.getByRole('heading', { name: 'Inspect T-0001' }).count(),
        0,
      );
      await page.unroute(production + '/api/v1/work/T-0001');
    },
  );
  assert.equal(errors.length, 0, JSON.stringify(errors));
  assert(!responses.some((r) => !r.expected), JSON.stringify(responses));
  assert(
    !requests.some(
      (r) =>
        !['GET', 'HEAD'].includes(r.method) &&
        new URL(r.url).pathname.startsWith('/api/v1'),
    ),
    JSON.stringify(requests),
  );
  assert(
    !requests.some(
      (r) =>
        ![new URL(base).origin, new URL(production).origin].includes(
          new URL(r.url).origin,
        ),
    ),
    JSON.stringify(requests),
  );
  fs.writeFileSync(
    out + '/result.json',
    JSON.stringify(
      {
        result: 'PASS',
        checks,
        errors,
        responses,
        requests,
        scope:
          'Compiled Chromium; authored visibility/focus events; fixture server and demo, not authenticated AEW integration',
      },
      null,
      2,
    ) + '\n',
  );
  await context.tracing.stop({ path: out + '/passed-trace.zip' });
} catch (e) {
  if (context)
    await context.tracing
      .stop({ path: out + '/failure-trace.zip' })
      .catch(() => {});
  fs.writeFileSync(
    out + '/result.json',
    JSON.stringify(
      {
        result: 'FAIL',
        scenario: current,
        error: String(e),
        checks,
        errors,
        responses,
        requests,
      },
      null,
      2,
    ) + '\n',
  );
  console.error(e);
  process.exitCode = 1;
} finally {
  await browser?.close();
  for (const child of owned) child.kill('SIGTERM');
}
