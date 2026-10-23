import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { URL } from 'node:url';

const base = process.env.STG02_BASE_URL ?? 'http://127.0.0.1:4253';
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base)) throw new Error('Synthetic loopback fixture target required');
const output = 'output/stg02';
await fs.mkdir(output, { recursive: true });
const read = async name => JSON.parse(await fs.readFile(`tests/fixtures/stg02/${name}`, 'utf8'));
const full = await read('continuation-full.json');
const partial = await read('continuation-partial.json');
const runRecording = await read('run.json');
const problems = await read('problems.json');
const results = [];
const owned = [];
if (process.env.STG02_SPAWN_FIXTURES === '1') {
  if (!process.env.STG02_PYTHON || !process.env.STG02_DESIGNER_DRIVER) throw new Error('Explicit fixture Python and designer driver required');
  const port = Number(new URL(base).port);
  const launch = args => {
    const child = spawn(process.env.STG02_PYTHON, ['-I', '-B', ...args], { cwd: '..', stdio: ['ignore', 'inherit', 'inherit'], windowsHide: true, timeout: 180000 });
    owned.push(child);
    return child;
  };
  launch([process.env.STG02_DESIGNER_DRIVER, '--port', String(port + 1)]);
  launch(['docs/stg02/serve_recordings.py', '--port', String(port), '--upstream-port', String(port + 1), '--web-root', process.env.STG02_WEB_ROOT ?? 'web/dist-stg02', '--lifetime', '180']);
  const until = Date.now() + 10000;
  let ready = false;
  while (Date.now() < until) {
    try { if ((await globalThis.fetch(base + '/stg02', { signal: globalThis.AbortSignal.timeout(1000) })).ok) { ready = true; break; } } catch { /* Bounded process readiness only. */ }
    await new Promise(done => globalThis.setTimeout(done, 100));
  }
  if (!ready) { for (const child of owned) child.kill(); throw new Error('Owned synthetic preview failed to start'); }
}
const browser = await chromium.launch({ headless: true,
  executablePath: process.env.CHROMIUM_PATH ?? 'artifacts/playwright/browsers/chromium-1217/chrome-linux64/chrome',
  args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const deadline = globalThis.setTimeout(() => { void browser.close(); }, 120000);
try {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, serviceWorkers: 'block' });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', failure => errors.push(String(failure)));
    await page.goto(base + '/stg02');
    await page.getByRole('heading', { name: /waiting.*continuation/i }).waitFor();
    await page.getByRole('link', { name: 'Inspect supplied execution invocation:demo-1' }).waitFor();
    await page.screenshot({ path: `${output}/${width}-waiting.png`, fullPage: true });
    await page.getByRole('link', { name: 'Inspect supplied execution invocation:demo-1' }).click();
    await page.getByRole('heading', { name: 'Remote effect', exact: true }).waitFor();
    assert.match(await page.locator('main').innerText(), /UNKNOWN_EFFECT/);
    assert.match(await page.locator('main').innerText(), /IF12:provider-timeout:demo1/);
    await page.screenshot({ path: `${output}/${width}-run-unknown.png`, fullPage: true });
    const stale = JSON.parse(JSON.stringify(runRecording));
    const markStale = value => {
      if (!value || typeof value !== 'object') return;
      if ('fact_ref' in value && 'qualification' in value && 'observation_state' in value) {
        value.qualification = 'unqualified'; value.observation_state = 'stale'; value.authority_class = 'unqualified_report'; value.governing_owner = null;
      }
      for (const child of Object.values(value)) markStale(child);
    };
    markStale(stale);
    stale.outcome = 'historical'; stale.continuity = 'revalidate_required'; stale.limitations = ['historical_only'];
    await page.route('**/v1/read/runs/**', route => route.fulfill({ status: 200, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'private, no-store', 'X-AEW-Wire-Version': '0.3.4' }, body: JSON.stringify(stale) }));
    await page.reload();
    await page.getByRole('heading', { name: 'Read outcome: historical', exact: true }).waitFor();
    assert.match(await page.locator('main').innerText(), /stale · unqualified/);
    await page.screenshot({ path: `${output}/${width}-stale.png`, fullPage: true });
    await page.unroute('**/v1/read/runs/**');
    for (const outcome of ['unavailable', 'unsupported']) {
      const limited = { ...runRecording, outcome, continuity: 'unknown', items: [], limitations: outcome === 'unavailable' ? ['source_unavailable'] : [] };
      await page.route('**/v1/read/runs/**', route => route.fulfill({ status: 200, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'private, no-store', 'X-AEW-Wire-Version': '0.3.4' }, body: JSON.stringify(limited) }));
      await page.reload();
      await page.getByRole('heading', { name: `Read outcome: ${outcome}`, exact: true }).waitFor();
      assert.equal(await page.getByRole('alert').count(), 0);
      await page.screenshot({ path: `${output}/${width}-empty-run-${outcome}.png`, fullPage: true });
      await page.unroute('**/v1/read/runs/**');
    }
    await page.goto(base + '/stg02?view=continuation&id=ticket%3Aone');
    await page.getByRole('heading', { name: 'AEV: unknown', exact: true }).waitFor();
    assert.match(await page.locator('main').innerText(), /SOURCE_UNAVAILABLE/);
    await page.screenshot({ path: `${output}/${width}-partial-owner.png`, fullPage: true });
    for (const [name, recording] of [['provided', full], ['partial', partial]]) {
      await page.route('**/v1/read/continuation-state/**', route => route.fulfill({ status: recording.status, headers: recording.headers, body: JSON.stringify(recording.body) }));
      await page.reload();
      await page.getByRole('heading', { name: `Read outcome: ${recording.body.outcome}`, exact: true }).waitFor();
      assert.match(await page.locator('main').innerText(), /Information only — never permission/);
      await page.screenshot({ path: `${output}/${width}-${name}.png`, fullPage: true });
      await page.unroute('**/v1/read/continuation-state/**');
    }
    for (const [name, filename, phrase] of [
      ['index-first', 'index-first.json', 'More pages follow.'],
      ['index-last', 'index-last.json', 'Complete for the requested recipient scope.'],
      ['index-partial', 'index-partial.json', 'Incomplete membership:'],
      ['index-empty', 'index-empty.json', 'None in the requested recipient scope.'],
    ]) {
      const recording = await read(filename);
      await page.route('**/v1/read/owner-operations*', route => route.fulfill({ status: 200, headers: recording.headers, body: JSON.stringify(recording.body) }));
      await page.goto(base + '/stg02?view=operations');
      await page.getByRole('heading', { name: `Read outcome: ${recording.body.outcome}`, exact: true }).waitFor();
      assert.ok((await page.locator('main').innerText()).includes(phrase));
      await page.getByRole('heading', { name: 'Collection basis — aggregation only', exact: true }).waitFor();
      const basisText = await page.getByRole('heading', { name: 'Collection basis — aggregation only', exact: true }).locator('..').innerText();
      assert.ok(basisText.includes(recording.body.collection_basis?.fact_ref ?? 'Not supplied'));
      if (name === 'index-first') assert.equal(await page.getByRole('link', { name: 'Next supplied page' }).count(), 1);
      await page.screenshot({ path: `${output}/${width}-${name}.png`, fullPage: true });
      await page.unroute('**/v1/read/owner-operations*');
    }
    for (const [name, status] of [['denied', 404], ['unavailable', 503]]) {
      const specimen = problems.find(item => item.status === status && item.route === '/v1/read/continuation-state/{work_id}');
      assert.ok(specimen);
      await page.route('**/v1/read/continuation-state/**', route => route.fulfill({ status, headers: specimen.headers, body: JSON.stringify(specimen.body) }));
      await page.goto(base + '/stg02?view=continuation&id=ticket%3Aone');
      await page.getByRole('alert').waitFor();
      if (status === 404) assert.match(await page.getByRole('alert').innerText(), /Not found or not disclosable/);
      assert.equal(await page.getByRole('heading', { name: 'AEV: unknown', exact: true }).count(), 0);
      await page.screenshot({ path: `${output}/${width}-${name}.png`, fullPage: true });
      await page.unroute('**/v1/read/continuation-state/**');
    }
    await page.goto(base + '/stg02');
    await page.getByRole('heading', { name: 'Protected actions — held', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: /close attachment|reattach|attach lead/i }).count(), 0);
    await page.getByRole('button', { name: 'Review work supplied by the fixture delegation', exact: true }).click();
    const submit = page.getByRole('button', { name: 'Submit selected work to HEB', exact: true });
    assert.equal(await submit.isDisabled(), true);
    await page.getByRole('checkbox').check();
    await submit.click();
    await page.getByRole('heading', { name: '202 — received, not done', exact: true }).waitFor();
    await page.screenshot({ path: `${output}/${width}-received-held.png`, fullPage: true });
    const ownerLink = page.getByRole('link', { name: /^Inspect exact owner outcome:/ });
    await ownerLink.waitFor();
    const ownerResponse = page.waitForResponse(response => response.url().includes('/o01/v0/owner-operations/'));
    await ownerLink.click();
    const ownerBody = await (await ownerResponse).json();
    await page.getByRole('heading', { name: `Read outcome: ${ownerBody.result.effect_state}`, exact: true }).waitFor();
    const ownerUrl = page.url();
    await page.reload();
    await page.getByRole('heading', { name: /^Read outcome:/ }).waitFor();
    assert.equal(page.url(), ownerUrl);
    await page.screenshot({ path: `${output}/${width}-reloaded-owner.png`, fullPage: true });
    const contradictory = globalThis.structuredClone(ownerBody);
    contradictory.result.operation_ref = 'op:other';
    contradictory.result.effect_state = 'EFFECT_CONFIRMED';
    await page.route('**/o01/v0/owner-operations/**', route => route.fulfill({ status: 200, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'private, no-store', 'X-AEW-O01-Wire': 'o01-command-0.2-review-candidate' }, body: JSON.stringify(contradictory) }));
    await page.reload();
    assert.match(await page.getByRole('alert').innerText(), /binding/);
    assert.equal(await page.getByRole('heading', { name: 'Read outcome: EFFECT_CONFIRMED', exact: true }).count(), 0);
    await page.screenshot({ path: `${output}/${width}-owner-binding-rejected.png`, fullPage: true });
    await page.unroute('**/o01/v0/owner-operations/**');
    for (const [code, status] of [['invalid_request', 400], ['not_found_or_not_disclosable', 404], ['request_key_conflict', 409], ['unsupported_action', 400], ['unresolved_no_redispatch', 409]]) {
      await page.evaluate(() => globalThis.sessionStorage.clear());
      let posts = 0;
      await page.route('**/o01/v0/command-sets', route => {
        posts++;
        return route.fulfill({ status, headers: { 'Content-Type': 'application/problem+json', 'Cache-Control': 'private, no-store', 'X-AEW-O01-Wire': 'o01-command-0.2-review-candidate' }, body: JSON.stringify({ code, status, retry: 'never', type: 'about:blank', title: 'Request could not be completed', correlation_id: 'correlation:one' }) });
      });
      await page.goto(base + '/stg02');
      await page.getByRole('button', { name: 'Review work supplied by the fixture delegation', exact: true }).click();
      await page.getByRole('checkbox').check();
      await page.getByRole('button', { name: 'Submit selected work to HEB', exact: true }).click();
      await page.getByRole('alert').waitFor();
      assert.equal(await page.getByRole('button', { name: 'Reconcile using the same key and exact body' }).isDisabled(), true);
      await page.reload();
      await page.getByText(`Retry guidance: never · ${code}`, { exact: true }).waitFor();
      assert.equal(await page.getByRole('button', { name: 'Reconcile using the same key and exact body' }).isDisabled(), true);
      assert.equal(posts, 1);
      await page.screenshot({ path: `${output}/${width}-terminal-${code}.png`, fullPage: true });
      await page.unroute('**/o01/v0/command-sets');
    }
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1), false);
    assert.deepEqual(errors, []);
    results.push({ width, waiting: true, runUnknown: true, continuation: true, nondisclosing404: true, unavailable503: true,
      protectedControlCount: 0, separateSelection: true, receipt202: true, reloadedOwner: true, emptyLimitedRuns: true,
      terminalCodesAcrossReload: 5, rejectedContradictoryOwner: true, collectionBasis: true,
      source: 'compiled fixture build; source/build provenance must be recorded separately' });
    await context.close();
  }
} finally { globalThis.clearTimeout(deadline); await browser.close(); for (const child of owned) child.kill(); }
await fs.writeFile(`${output}/results.json`, JSON.stringify({ base, results }, null, 2) + '\n');
console.log(JSON.stringify(results));
