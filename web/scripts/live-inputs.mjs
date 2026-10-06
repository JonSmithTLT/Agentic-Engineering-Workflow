import fs from 'node:fs';
import path from 'node:path';
import { Buffer } from 'node:buffer';

// Only fixed diagnostics escape this boundary: JSON/parser/fs errors may carry secrets.
export function targetOrigin(value) {
  try {
    const url = new globalThis.URL(value);
    if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' ||
        url.username || url.password || url.pathname !== '/' || url.search || url.hash)
      throw new Error();
    return url.origin;
  } catch {
    throw new Error('LIVE_TARGET_INVALID');
  }
}

export function sessionCookie(file, origin) {
  let fd;
  try {
    // Reject symlinks and non-files; open/read one descriptor, bounded before parsing.
    if (!fs.lstatSync(file).isFile()) throw new Error();
    fd = fs.openSync(file, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW ?? 0));
    const stat = fs.fstatSync(fd);
    if (!stat.isFile() || stat.size > 4096 || stat.size === 0 ||
        (process.platform !== 'win32' && ((stat.mode & 0o077) !== 0 || stat.uid !== process.getuid())))
      throw new Error();
    const bytes = Buffer.alloc(4097);
    const size = fs.readSync(fd, bytes, 0, bytes.length, 0);
    if (size > 4096) throw new Error();
    const input = JSON.parse(bytes.subarray(0, size).toString('utf8'));
    if (Object.keys(input).sort().join(',') !== 'cookie,origin,version' || input.version !== 1 ||
        input.origin !== origin || Object.keys(input.cookie).sort().join(',') !== 'name,value' ||
        input.cookie.name !== 'aew_session' || typeof input.cookie.value !== 'string' ||
        !/^aew1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(input.cookie.value)) throw new Error();
    return { name: 'aew_session', value: input.cookie.value, url: origin,
      httpOnly: true, sameSite: 'Strict', secure: false };
  } catch {
    throw new Error('LIVE_SESSION_FILE_INVALID');
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
  }
}

export function safeOutput(file, cookieFile) {
  // A caller must never accidentally overwrite the private input with evidence.
  const identity = p => fs.existsSync(p) ? fs.realpathSync(p) : path.resolve(p);
  if (identity(file) === identity(cookieFile)) throw new Error('LIVE_OUTPUT_INVALID');
  if (fs.existsSync(file)) {
    const output = fs.statSync(file), input = fs.statSync(cookieFile);
    if (output.dev === input.dev && output.ino === input.ino) throw new Error('LIVE_OUTPUT_INVALID');
  }
  fs.mkdirSync(path.dirname(path.resolve(file)), { recursive: true });
  return file;
}

export function permittedRequest(url, method, origin) {
  const u = new globalThis.URL(url);
  return u.origin === origin && ['GET', 'HEAD'].includes(method) &&
    !u.pathname.startsWith('/session/') && !u.pathname.startsWith('/api/preview/') &&
    !u.pathname.includes('mockServiceWorker') && !u.searchParams.has('fixture');
}
