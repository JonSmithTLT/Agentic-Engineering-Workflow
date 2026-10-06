import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { targetOrigin, sessionCookie, safeOutput, permittedRequest } from './live-inputs.mjs';

const origin = 'http://127.0.0.1:4280';
test('target cannot contain credentials, paths, queries or foreign hosts', () => {
  assert.equal(targetOrigin(origin + '/'), origin);
  for (const value of ['http://user:secret@127.0.0.1:4280', origin + '/session/secret', origin + '?secret=x',
    origin + '#secret', 'https://example.com', 'http://localhost:4280', undefined]) {
    assert.throws(() => targetOrigin(value), { message: 'LIVE_TARGET_INVALID' });
  }
});

test('cookie file is narrow, origin-bound, private and never leaks parser errors', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'aew-live-input-'));
  const file = path.join(dir, 'cookie.json');
  const input = { version: 1, origin, cookie: { name: 'aew_session', value: 'aew1.test.privateSecret' } };
  const write = data => fs.writeFileSync(file, JSON.stringify(data), { mode: 0o600 });
  try {
    write(input);
    const cookie = sessionCookie(file, origin);
    assert.equal(cookie.value, input.cookie.value);
    assert.equal(cookie.url, origin);
    assert.equal(cookie.httpOnly, true);
    const bad = data => { write(data); assert.throws(() => sessionCookie(file, origin), { message: 'LIVE_SESSION_FILE_INVALID' }); };
    bad({ ...input, origin: 'http://127.0.0.1:4281' });
    bad({ ...input, cookie: { ...input.cookie, name: 'other' } });
    bad({ ...input, cookie: { ...input.cookie, value: 'secret\nheader' } });
    bad({ ...input, storageState: { secret: true } });
    bad({ ...input, cookie: { ...input.cookie, path: '/api' } });
    fs.writeFileSync(file, 'privateSecret {');
    assert.throws(() => sessionCookie(file, origin), { message: 'LIVE_SESSION_FILE_INVALID' });
    fs.writeFileSync(file, 'x'.repeat(4097));
    assert.throws(() => sessionCookie(file, origin), { message: 'LIVE_SESSION_FILE_INVALID' });
    write(input);
    assert.throws(() => safeOutput(file, file), { message: 'LIVE_OUTPUT_INVALID' });
    if (process.platform !== 'win32') {
      fs.chmodSync(file, 0o644);
      assert.throws(() => sessionCookie(file, origin), { message: 'LIVE_SESSION_FILE_INVALID' });
      fs.chmodSync(file, 0o600);
      const link = path.join(dir, 'link.json');
      fs.symlinkSync(file, link);
      assert.throws(() => sessionCookie(link, origin), { message: 'LIVE_SESSION_FILE_INVALID' });
      const alias = path.join(dir, 'alias.json');
      fs.linkSync(file, alias);
      assert.throws(() => safeOutput(alias, file), { message: 'LIVE_OUTPUT_INVALID' });
    }
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});

test('browser guard allows only read-only same-origin production traffic', () => {
  assert.equal(permittedRequest(origin + '/api/v1/project', 'GET', origin), true);
  assert.equal(permittedRequest(origin + '/assets/index.js', 'GET', origin), true);
  for (const [url, method] of [[origin + '/api/v1/work', 'POST'], ['http://127.0.0.1:4281/api/v1/project', 'GET'],
    [origin + '/session/code', 'GET'], [origin + '/api/preview/journal/v0.1/entries', 'GET'],
    [origin + '/mockServiceWorker.js', 'GET'], [origin + '/work?fixture=F1', 'GET']])
    assert.equal(permittedRequest(url, method, origin), false);
});
