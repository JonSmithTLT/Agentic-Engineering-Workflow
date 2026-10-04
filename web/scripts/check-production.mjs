import fs from 'node:fs';
import path from 'node:path';
function files(dir) {
  return fs
    .readdirSync(dir, { withFileTypes: true })
    .flatMap((entry) =>
      entry.isDirectory()
        ? files(path.join(dir, entry.name))
        : [path.join(dir, entry.name)],
    );
}
for (const file of files('dist')) {
  const text = fs.readFileSync(file, 'utf8');
  if (/execution-preview|execution-fixtures|TRACE-Clangd|Inspect recorded execution|Supplied execution controls|Recorded investigation|\/api\/preview\/execution/.test(text)) throw new Error('Production execution preview leakage: '+file);
  if (/evidence-preview|\/api\/preview\/evidence|REF-J05-|Evidence inspection preview|Inspect evidence|Excerpt SHA-256 verified/.test(text)) throw new Error(`Production evidence preview leakage: ${file}`);
  if (/investigation-preview|\/api\/preview\/investigation|SRC-Removal|PKT-Retry|No delivery receipt supplied|Compare invocations/.test(text)) throw new Error(`Production investigation leakage: ${file}`);
  if (
    /aew-demo-transport|X-AEW-Demo-Fixture|journal-preview|\/api\/preview\/journal|FUTURE_JOURNAL_KIND|CLANGD-E871|Journal scenario|Explore bounded origin graph|journal-fixtures|W01_REPLAY_CATALOG|Manual replay|Contract Playground|scenario-config|mockServiceWorker|setupWorker|Demo data|project:demo\/aew|aew-demo|FUTURE_WORK_STATE|attacker\.invalid|Mock Service Worker/.test(
      text,
    )
  )
    throw new Error(`Production mock leakage: ${file}`);
}
console.log('Production build excludes fixtures and mock initialization');
