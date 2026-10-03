import fs from 'node:fs';
import crypto from 'node:crypto';
import { z } from 'zod';
import { journalSchemas, journalCases } from '../src/api/preview/journal/schema.ts';
import { journalFixture } from '../src/api/preview/journal/fixtures.ts';
const write = process.argv.includes('--write');
const sha = (text) => crypto.createHash('sha256').update(text).digest('hex');
function artifact(file, value) {
  const text = JSON.stringify(value, null, 2) + '\n';
  if (write) fs.writeFileSync(file, text);
  else if (fs.readFileSync(file, 'utf8') !== text) throw new Error(`Journal artifact drift: ${file}`);
  return sha(text);
}
const digest = artifact('docs/design/journal-preview-0.1.0.json', {
  id: 'journal-preview', version: '0.1.0', disposition: 'PROVISIONAL',
  routes: { base: '/api/preview/journal/v0.1', methods: ['GET', 'HEAD'], collection: '/entries?limit=50', detail: '/entries/{id}', filters: ['component', 'component_missing=1', 'kind', 'cursor', 'case'] },
  ordering: ['published_at DESC', 'id ASC', 'null published_at: final Undated group, id ASC'],
  rules: ['Component identity and publication time are supplied; other timestamps never substitute.', 'supporting_evidence and opposing_evidence define source roles only.', 'Prompt metadata only; raw prompts are not supported.', 'No retention explanation supplied when no explanation is supplied.', 'Canonical decisions remain references to their authoritative records. “Included in context” references do not establish delivery, use, or benefit.'],
  schemas: Object.fromEntries(Object.entries(journalSchemas).map(([key, schema]) => [key, z.toJSONSchema(schema)])),
});
artifact('docs/design/journal-fixtures.manifest.json', {
  contract: 'journal-preview', version: '0.1.0', sha256: digest,
  cases: Object.fromEntries(journalCases.map((name) => [name, { entries: journalFixture(name).length, sha256: sha(JSON.stringify(journalFixture(name))) }])),
});
console.log('Journal preview schema and fixture digests match');
