/** File-link, inventory and retained-byte checks. No network or Git dependency. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const catalog = JSON.parse(fs.readFileSync(path.join(root, 'web/docs/reference/documents.json'), 'utf8'));
const original = new Map(), destinations = new Set(), errors = [];
const add = (message) => errors.push(message);
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
for (const entry of catalog.entries) {
  if (original.has(entry.original_path)) add(`Duplicate original: ${entry.original_path}`);
  original.set(entry.original_path, entry.path);
  if (destinations.has(entry.path)) add(`Duplicate destination: ${entry.path}`);
  destinations.add(entry.path);
  const file = path.resolve(root, entry.path);
  if (!entry.path.startsWith('web/docs/') || !file.startsWith(root + path.sep)) {
    add(`Invalid catalog path: ${entry.path}`); continue;
  }
  if (!fs.existsSync(file)) { add(`Missing document: ${entry.path}`); continue; }
  if (entry.retained_sha256 && hash(fs.readFileSync(file)) !== entry.retained_sha256) add(`Retained bytes changed: ${entry.path}`);
}
for (const name of catalog.new_documents) {
  if (destinations.has(name)) add(`Duplicate registration: ${name}`);
  destinations.add(name);
  if (!name.startsWith('web/docs/') || !fs.existsSync(path.join(root, name))) add(`Missing new document: ${name}`);
}
for (const name of catalog.stable_contract_paths) {
  if (original.get(name) !== name) add(`Contract-pinned path moved: ${name}`);
}
// Git is optional in the source-only offline gate. Never inventory private local files.
let tracked;
try { tracked = execFileSync('git', ['ls-files', '-z', '--', 'web/docs'], { cwd: root, stdio: ['ignore', 'pipe', 'ignore'] }).toString().split('\0').filter(Boolean); }
catch { tracked = [...destinations]; }
for (const name of tracked) if (!destinations.has(name)) add(`Tracked document not cataloged: ${name}`);

const known = new Set(catalog.known_missing_links.map((item) => `${item.document}\0${item.target}`));
for (const name of destinations) {
  if (!name.endsWith('.md') || !fs.existsSync(path.join(root, name))) continue;
  const text = fs.readFileSync(path.join(root, name), 'utf8').replace(/```[\s\S]*?```/g, '');
  const links = [...text.matchAll(/!?\[[^\]\n]*\]\((<[^>]+>|[^\s)]+)(?:\s+"[^"]*")?\)/g)].map((match) => match[1]);
  const definitions = [...text.matchAll(/^\s*\[[^\]]+\]:\s*(<[^>]+>|\S+)/gm)].map((match) => match[1]);
  for (let target of [...links, ...definitions]) {
    target = target.replace(/^<|>$/g, '');
    if (/^(?:[a-z][a-z\d+.-]*:|#|\/\/)/i.test(target)) continue;
    let withoutFragment;
    try { withoutFragment = decodeURIComponent(target.split(/[?#]/)[0]); }
    catch { add(`Invalid URL encoding: ${name} -> ${target}`); continue; }
    if (!withoutFragment) continue;
    const resolved = path.resolve(path.dirname(path.join(root, name)), withoutFragment);
    if (!resolved.startsWith(root + path.sep)) { add(`Link leaves repository: ${name} -> ${target}`); continue; }
    if (fs.existsSync(resolved)) continue;
    // Frozen reports may retain then-current relative navigation; resolve only a supplied relocation.
    const previous = catalog.entries.find((entry) => entry.path === name)?.original_path;
    if (previous) {
      const oldTarget = path.relative(root, path.resolve(path.dirname(path.join(root, previous)), withoutFragment)).replaceAll(path.sep, '/');
      const moved = original.get(oldTarget);
      if (moved && fs.existsSync(path.join(root, moved))) continue;
    }
    if (!known.has(`${name}\0${target}`)) add(`Broken file link: ${name} -> ${target}`);
  }
}
if (errors.length) { process.stderr.write(errors.join('\n') + '\n'); process.exitCode = 1; }
else process.stdout.write(`Documentation PASS: ${catalog.entries.length} retained entries, ${catalog.new_documents.length} new documents; protected bytes and local file links checked.\n`);
