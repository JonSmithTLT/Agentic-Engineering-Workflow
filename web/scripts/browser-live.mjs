/** F20.6 production/live checks. Owns browsers only; never starts or mocks a server. */
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
import { chromium, request } from 'playwright';
import { responseSchemas } from '../src/api/schema.ts';
import { targetOrigin, sessionCookie, safeOutput, permittedRequest, writeReport } from './live-inputs.mjs';

const checks = [];
const skipped = [];
let stage = 'input-validation', browser, output;
const counts = { blocked_requests: 0, page_errors: 0, console_errors: 0, invalid_responses: 0, api_responses: 0 };
const pages = [
  ['/', 'Overview', 'overview'], ['/work', 'Work', 'work'], ['/runs', 'Runs', 'runs'],
  ['/evidence', 'Evidence', 'evidence'], ['/knowledge', 'Knowledge', 'knowledge'],
  ['/history', 'History / integrity', 'history'], ['/attention', 'Attention', 'action_projection'],
  ['/queue', 'Queue', 'queue'],
];
const headings = { overview: 'Overview', work: 'Work investigation', runs: 'Runs investigation',
  evidence: 'Evidence', knowledge: 'Knowledge', history: 'History', action_projection: 'Attention', queue: 'Queue' };
const listSchemas = { work: 'WorkListResponse', runs: 'InvocationListResponse', evidence: 'EvidenceListResponse',
  knowledge: 'KnowledgeListResponse', history: 'HistoryListResponse', attention: 'AttentionListResponse', activity: 'ActivityListResponse' };
function schemaFor(url) {
  const parts = new globalThis.URL(url).pathname.slice('/api/v1/'.length).split('/');
  if (parts.join('/') === 'history/integrity') return responseSchemas.IntegrityResponse;
  if (parts[0] === 'project') return responseSchemas.ProjectResponse;
  if (parts[0] === 'capabilities') return responseSchemas.CapabilitiesResponse;
  if (parts[0] === 'overview') return responseSchemas.OverviewResponse;
  const detail = { work: 'WorkResponse', runs: 'InvocationResponse', evidence: 'EvidenceResponse',
    knowledge: 'KnowledgeResponse', history: 'HistoryResponse' };
  return responseSchemas[parts.length === 1 ? listSchemas[parts[0]] : detail[parts[0]]];
}
function requirePass(condition) { assert(condition, 'LIVE_CHECK_FAILED'); }

try {
  requirePass(process.versions.node.split('.')[0] === '22');
  const origin = targetOrigin(process.env.DASHBOARD_BASE_URL);
  const file = process.env.DASHBOARD_SESSION_FILE;
  const cookie = sessionCookie(file, origin);
  output = safeOutput(process.env.DASHBOARD_LIVE_OUTPUT ?? 'output/live/browser-live.json', file);
  stage = 'accepted-contract-pin';
  const pin = JSON.parse(fs.readFileSync('src/api/contract-version.json', 'utf8'));
  const digest = createHash('sha256').update(fs.readFileSync('../docs/design/dashboard-api-v1-provisional.yaml')).digest('hex');
  requirePass(pin.approval === 'ACCEPTED' && pin.sha256 === digest);
  const revision = JSON.parse(fs.readFileSync('node_modules/playwright-core/browsers.json', 'utf8'))
    .browsers.find(b => b.name === 'chromium').revision;
  stage = 'browser-launch';
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? process.env.PLAYWRIGHT_BROWSER_EXECUTABLE ??
    path.resolve(`artifacts/playwright/browsers/chromium-${revision}/chrome-linux64/chrome`) });

  stage = 'unauthenticated-api-refusal';
  const anonymous = await request.newContext({ baseURL: origin, maxRedirects: 0, timeout: 15000 });
  try {
    const response = await anonymous.get('/api/v1/project');
    requirePass(response.status() === 401);
    requirePass((await response.json()).code === 'SESSION_REQUIRED');
  } finally { await anonymous.dispose(); }
  checks.push('Unauthenticated project request is refused with SESSION_REQUIRED');

  let project, capabilities;
  for (const [layout, viewport] of [['desktop', { width: 1440, height: 1000 }], ['phone', { width: 390, height: 844 }]]) {
    stage = `${layout}-authenticated-bootstrap`;
    const context = await browser.newContext({ viewport, serviceWorkers: 'block', permissions: ['clipboard-read', 'clipboard-write'] });
    const pending = new Set();
    let refusing = false;
    try {
      await context.addCookies([cookie]);
      // This guard aborts unsafe traffic. It never fulfills/rewrites a response.
      await context.route('**/*', route => {
        const r = route.request();
        if (permittedRequest(r.url(), r.method(), origin)) return route.continue();
        counts.blocked_requests++;
        return route.abort();
      });
      function observe(page) {
        page.setDefaultTimeout(15000);
        page.on('pageerror', () => counts.page_errors++);
        page.on('console', m => { if (m.type() === 'error' && !refusing) counts.console_errors++; });
        page.on('response', response => {
          if (!new globalThis.URL(response.url()).pathname.startsWith('/api/v1/')) return;
          const task = (async () => {
            counts.api_responses++;
            if (refusing && response.status() === 401) return;
            if (response.status() === 304) return;
            if (response.status() !== 200) { counts.invalid_responses++; return; }
            try {
              const schema = schemaFor(response.url());
              if (!schema) throw new Error();
              const body = schema.parse(await response.json());
              if (project && body.project_id !== project.project_id) throw new Error();
            } catch { counts.invalid_responses++; }
          })();
          pending.add(task);
          void task.finally(() => pending.delete(task));
        });
      }
      context.on('page', observe);
      const page = await context.newPage();
      async function projection(route, schema) {
        const result = await context.request.get(origin + '/api/v1' + route, { maxRedirects: 0 });
        requirePass(result.status() === 200);
        const body = schema.parse(await result.json());
        if (project) requirePass(body.project_id === project.project_id);
        return body;
      }
      project = await projection('/project', responseSchemas.ProjectResponse);
      capabilities = (await projection('/capabilities', responseSchemas.CapabilitiesResponse)).data;
      requirePass(capabilities.overview?.state === 'AVAILABLE');
      // Bootstrap through the compiled UI too, not only the API request context.
      await page.goto(origin, { waitUntil: 'domcontentloaded' });
      await page.locator('main').getByRole('heading', { name: 'Overview', exact: true }).waitFor();
      await page.locator('header').getByText(project.data.name, { exact: true }).waitFor();
      await page.locator('main').getByRole('status').filter({ hasText: /^CURRENT$/ }).first().waitFor();
      checks.push(`${layout}: authenticated accepted-project bootstrap through production UI`);

      for (const [route, label, capability] of pages) {
        stage = `${layout}-${capability}-navigation`;
        if (layout === 'phone') await page.getByRole('button', { name: 'Toggle navigation', exact: true }).click();
        const nav = page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: label, exact: true });
        await nav.focus();
        requirePass(await nav.evaluate(e => e === document.activeElement));
        await nav.press('Enter');
        await page.waitForURL(origin + route);
        await page.waitForLoadState('networkidle');
        const main = page.locator('main');
        await main.getByRole('heading', { level: 1, name: headings[capability], exact: true }).first().waitFor();
        const available = capabilities[capability]?.state === 'AVAILABLE';
        if (available) {
          if (capability === 'overview') await main.getByRole('heading', { name: 'Recent activity', exact: true }).waitFor();
          else if (capability !== 'queue') await main.getByRole('heading', { name: `${capability === 'action_projection' ? 'Attention' : label === 'History / integrity' ? 'History' : label} records`, exact: true }).waitFor();
          await main.getByRole('status').filter({ hasText: /^CURRENT$/ }).first().waitFor();
          if (!['overview', 'queue', 'action_projection'].includes(capability)) {
            // Load the same page the UI requests; fixture IDs are never assumed.
            const list = await projection(`${route}?limit=100`, responseSchemas[listSchemas[route.slice(1)]]);
            if (list.data.items.length === 0) skipped.push(`${layout}:${capability}:record-selection (empty supplied page)`);
            else {
              stage = `${layout}-${capability}-record-link`;
              const record = list.data.items[0];
              const href = await main.locator('a[href]').evaluateAll((links, identity) => {
                const link = links.find(e => {
                  const u = new globalThis.URL(e.href);
                  return u.pathname === identity.route + '/' + identity.id ||
                    (u.pathname === identity.route && u.searchParams.get('selected') === identity.id);
                });
                return link?.getAttribute('href');
              }, { route, id: record.id });
              requirePass(!!href);
              const link = main.locator(`a[href=${JSON.stringify(href)}]`).first();
              await link.focus();
              await link.press('Enter');
              stage = `${layout}-${capability}-record-detail`;
              await page.waitForURL(url => url.pathname === route + '/' + record.id || url.searchParams.get('selected') === record.id);
              const title = capability === 'work' || capability === 'knowledge' ? record.title :
                capability === 'history' ? record.title ?? record.id : record.id;
              await main.getByRole('heading', { level: 1, name: title, exact: true }).last().waitFor();
              await main.getByRole('status').filter({ hasText: /^CURRENT$/ }).first().waitFor();
              if (capability === 'work') {
                if (layout === 'phone') {
                  stage = 'phone-work-heading-focus';
                  await page.waitForFunction(() => {
                    const selected = document.activeElement;
                    return selected?.matches('[data-work-heading]') &&
                      selected.getBoundingClientRect().top >= document.querySelector('.project-header').getBoundingClientRect().bottom;
                  });
                }
                await main.getByRole('button', { name: 'Copy dashboard link', exact: true }).click();
                const pinned = await page.evaluate(() => navigator.clipboard.readText());
                const pinnedUrl = new globalThis.URL(pinned);
                requirePass(pinnedUrl.origin === origin && pinnedUrl.pathname === route && pinnedUrl.searchParams.get('selected') === record.id);
                stage = `${layout}-work-copy-reopen`;
                const reopened = await context.newPage();
                try {
                  await reopened.goto(pinned, { waitUntil: 'domcontentloaded' });
                  await reopened.locator('main').getByRole('heading', { level: 1, name: title, exact: true }).last().waitFor();
                  await reopened.locator('main').getByRole('status').filter({ hasText: /^CURRENT$/ }).first().waitFor();
                  await reopened.waitForLoadState('networkidle');
                  await Promise.all([...pending]);
                  requirePass(counts.page_errors === 0 && counts.console_errors === 0 && counts.invalid_responses === 0 && counts.blocked_requests === 0);
                } finally { await reopened.close(); }
                checks.push(`${layout}: Work copied selection reloads against the same authenticated origin`);
              }
              await page.goBack({ waitUntil: 'domcontentloaded' });
              await page.waitForURL(origin + route);
              await page.waitForLoadState('networkidle');
              checks.push(`${layout}:${capability}: supplied first-page record opens and browser Back restores its collection`);
            }
          }
        } else {
          await main.getByRole('heading', { name: 'Data unavailable', exact: true }).first().waitFor();
        }
        requirePass(await main.getByRole('alert').count() === 0);
        requirePass(await page.getByText('Demo data', { exact: true }).count() === 0);
        requirePass(await page.getByText('Journal', { exact: true }).count() === 0);
        const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
        requirePass(fits);
        checks.push(`${layout}:${capability}: keyboard navigation, capability state, no page overflow or demo UI`);
      }
      stage = `${layout}-themes`;
      if (layout === 'phone') await page.getByRole('button', { name: 'Toggle navigation', exact: true }).click();
      for (const theme of ['dark', 'light']) {
        await page.getByLabel('Appearance', { exact: true }).selectOption(theme);
        requirePass(await page.evaluate(t => document.documentElement.dataset.theme === t, theme));
      }
      checks.push(`${layout}: shared native Appearance control switches both themes`);
      await Promise.all([...pending]);
      requirePass(counts.invalid_responses === 0 && counts.console_errors === 0 && counts.page_errors === 0);
      stage = `${layout}-session-refusal-ui`;
      refusing = true;
      await context.clearCookies();
      await page.goto(origin + '/work', { waitUntil: 'domcontentloaded' });
      await page.locator('main').getByRole('alert').filter({ hasText: 'Session required (401)' }).waitFor();
      requirePass(await page.locator('main').getByRole('table').count() === 0);
      checks.push(`${layout}: missing session shows refusal and no Work table`);
      // Refusal is expected only after explicitly clearing this context's cookie.
      await Promise.all([...pending]);
      requirePass((await page.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).length)) === 0);
    } finally { await context.close(); }
  }
  stage = 'final-validation';
  requirePass(counts.blocked_requests === 0 && counts.page_errors === 0);
  stage = 'report-write';
  requirePass(writeReport(output, { status: 'PASS', mode: 'authenticated-live-production',
    contract_version: pin.version, contract_sha256: digest, browser_version: browser.version(),
    checks, skipped, counts, limitations: [
      'BUILD.json/source provenance and main-line security negative controls must be recorded by F20.6.',
      'No screenshots, traces, HAR, response bodies, request headers or credentials are captured.',
      'Hostile-content datasets, validator/session replacement isolation, expiry and conditional-request guarantees require separate main-line acceptance checks.',
    ] }));
  console.log(`PASS authenticated live browser checks (${checks.length}); see sanitized report`);
} catch {
  // Never print Playwright, schema, URL or filesystem exception details.
  if (output) writeReport(output, { status: 'FAIL', mode: 'authenticated-live-production',
    failed_stage: stage, checks, skipped, counts });
  console.error(`FAIL authenticated live browser checks: ${stage}`);
  process.exitCode = 1;
} finally { if (browser) await browser.close(); }
