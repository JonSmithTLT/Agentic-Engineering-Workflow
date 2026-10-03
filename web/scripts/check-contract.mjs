import fs from 'node:fs';
import { createHash } from 'node:crypto';
import yaml from 'yaml';
const artifact = fs.readFileSync(
  '../docs/design/dashboard-api-v1-provisional.yaml',
  'utf8',
);
const approval = JSON.parse(fs.readFileSync('docs/c0-approval.json', 'utf8'));
const version = JSON.parse(
  fs.readFileSync('src/api/contract-version.json', 'utf8'),
);
const digest = createHash('sha256').update(artifact).digest('hex');
if (
  approval.status !== 'ACCEPTED' ||
  approval.sha256 !== digest ||
  version.sha256 !== digest ||
  version.approval !== 'ACCEPTED' ||
  yaml.parse(artifact).info.version !== approval.contract_version ||
  version.version !== approval.contract_version
)
  throw new Error(
    'Contract drift: renewed C0 acceptance and companion artifacts are required',
  );
console.log(`Accepted API ${version.version}: ${digest}`);
