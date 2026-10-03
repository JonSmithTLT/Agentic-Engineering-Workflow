import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const base = process.env.DASHBOARD_PREVIEW_URL ?? 'http://127.0.0.1:4187';
const out = 'output/playwright-work-graph';
fs.mkdirSync(out, { recursive: true });
const revision = JSON.parse(
  fs.readFileSync('node_modules/playwright-core/browsers.json'),
).browsers.find((b) => b.name === 'chromium').revision;
const browser = await chromium.launch({
  executablePath: path.resolve(
    `artifacts/playwright/browsers/chromium-${revision}/chrome-linux64/chrome`,
  ),
});
const errors = [],
  requests = [],
  checks = [];
try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  const page = await context.newPage();
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });
  page.on('request', (r) =>
    requests.push({ url: r.url(), method: r.method() }),
  );
  await page.goto(base + '/work?view=graph&fixture=F1');
  const ticket = page.getByRole('button', { name: /^Select T-0001:/ });
  await ticket.waitFor();
  assert.equal(await page.locator('.graph-card').count(), 6);
  assert.equal(await page.locator('.graph-edges > path').count(), 5);
  const layout = await page
    .locator('.graph-card')
    .evaluateAll((nodes) =>
      nodes.map((n) => ({
        id: n.querySelector('code').textContent,
        x: n.getBoundingClientRect().x,
        w: n.getBoundingClientRect().width,
      })),
    );
  assert(
    layout.find((n) => n.id === 'E-0001').x <
      layout.find((n) => n.id === 'S-0001').x,
  );
  assert(
    layout.find((n) => n.id === 'S-0001').x <
      layout.find((n) => n.id === 'T-0001').x,
  );
  assert(layout.every((n) => n.w === 236));
  checks.push('Compiled CSP permits positioned cards and local SVG edges');
  await ticket.click();
  assert.equal(
    await page
      .getByRole('link', { name: 'Open Work detail' })
      .getAttribute('href'),
    '/work/T-0001?fixture=F1',
  );
  await page.getByRole('button', { name: 'Collapse branch S-0001' }).click();
  assert.equal(await ticket.count(), 0);
  await page
    .getByText('The selection is hidden by this focus or a collapsed branch.')
    .waitFor();
  await page.getByRole('button', { name: 'Expand all' }).click();
  await ticket.waitFor();
  await page
    .getByRole('combobox', { name: 'Graph focus' })
    .selectOption('S-0001');
  assert.equal(
    await page.getByRole('button', { name: /^Select E-0001:/ }).count(),
    0,
  );
  await page.reload();
  await ticket.waitFor();
  assert.equal(
    await page.getByRole('combobox', { name: 'Graph focus' }).inputValue(),
    'S-0001',
  );
  await page.getByRole('button', { name: 'Zoom out', exact: true }).click();
  assert.equal(await page.getByLabel('Zoom level').textContent(), '85%');
  checks.push(
    'Selection, collapse, expansion, zoom and focus deep-link reload',
  );
  await page.getByRole('combobox', { name: 'Graph focus' }).selectOption('');
  await ticket.click();
  await page.screenshot({ path: out + '/graph-light.png', fullPage: true });
  await page.getByRole('link', { name: 'Open Work detail' }).click();
  await page.reload();
  await page
    .getByRole('heading', {
      name: 'Validate projection consistency',
      exact: true,
    })
    .waitFor();
  checks.push('Selected record navigates to existing Work detail and reloads');
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto(base + '/work?view=graph&fixture=F1');
  await ticket.waitFor();
  await page.screenshot({ path: out + '/graph-dark.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Fit width', exact: true }).click();
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  );
  await page.screenshot({ path: out + '/graph-phone.png', fullPage: true });
  checks.push(
    'Light, dark and phone layouts; overflow confined to graph panel',
  );
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(base + '/work?view=graph&fixture=F6');
  await page.locator('.reference-card').waitFor();
  assert.equal(await page.locator('.graph-card').count(), 101);
  await page.locator('.reference-card .graph-select').click();
  await page
    .getByText(
      'This parent ID is supplied by a child record. Its own title, state and ancestors are not included in this page.',
    )
    .waitFor();
  const canvas = page.getByLabel('Work graph canvas');
  await canvas.focus();
  await page.keyboard.press('ArrowDown');
  assert((await canvas.evaluate((e) => e.scrollTop)) > 0);
  await page.screenshot({ path: out + '/graph-large.png', fullPage: true });
  const bounds = await canvas.boundingBox();
  const beforePan = await canvas.evaluate((e) => e.scrollTop);
  await page.mouse.move(bounds.x + bounds.width - 20, bounds.y + 300);
  await page.mouse.down();
  await page.mouse.move(bounds.x + bounds.width - 20, bounds.y + 150, {
    steps: 8,
  });
  await page.mouse.up();
  assert((await canvas.evaluate((e) => e.scrollTop)) > beforePan);
  await page.getByRole('button', { name: 'Next page', exact: true }).click();
  await page.getByRole('button', { name: /^Select T-1100:/ }).waitFor();
  assert.equal(await page.locator('.graph-card').count(), 101);
  checks.push(
    'Bounded 100-record pages, unloaded parent honesty, cursor pagination and keyboard/drag pan',
  );
  await page.goto(base + '/work?view=graph&fixture=F3');
  await page.getByRole('button', { name: /^Select T-0004:/ }).click();
  await page
    .getByText('Historical reference; never current evidence.', { exact: true })
    .waitFor();
  await page.goto(base + '/work?view=graph&fixture=F11');
  await page.locator('.graph-card .unknown').first().waitFor();
  checks.push(
    'Historical selection warns; unknown backend state stays explicit',
  );
  assert.deepEqual(errors, []);
  assert(
    !requests.some(
      (r) => r.url.includes('/api/v1/') && !['GET', 'HEAD'].includes(r.method),
    ),
  );
  assert(
    !requests.some(
      (r) => !r.url.startsWith(base + '/') && !r.url.startsWith('data:'),
    ),
  );
  assert(!requests.some((r) => r.url.includes('/api/v1/graph')));
  checks.push(
    'No CSP/browser errors, remote resources, mutation or new graph API',
  );
  fs.writeFileSync(
    out + '/browser-work-graph.json',
    JSON.stringify(
      {
        status: 'PASS',
        checks,
        errors,
        playwright: '1.59.1',
        chromium_revision: revision,
        browser_version: browser.version(),
        scope:
          'Compiled optional graph with mock accepted projections; not live AEW integration',
      },
      null,
      2,
    ) + '\n',
  );
  console.log(`PASS ${checks.length} graph browser checks`);
  await context.close();
} finally {
  await browser.close();
}
