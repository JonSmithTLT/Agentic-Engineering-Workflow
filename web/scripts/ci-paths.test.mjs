import { after, describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';

// Execute the workflow's actual inline detector, not a separately maintained copy.
const workflow = readFileSync(
  process.env.CI_PATHS_WORKFLOW ?? '../.github/workflows/web.yml',
  'utf8',
);
const block = workflow.split('        run: |\n')[1].split('\n\n  checks:')[0];
const detector = block
  .split('\n')
  .map((line) => line.slice(10))
  .join('\n');
const scratch = mkdtempSync(join(tmpdir(), 'w01-ci-paths-'));
const repo = join(scratch, 'repo');
mkdirSync(repo);
const git = (...args) =>
  execFileSync('git', args, { cwd: repo, encoding: 'utf8' }).trim();
git('init', '-q', '-b', 'main');
git('config', 'user.email', 'ci-probe@example.invalid');
git('config', 'user.name', 'CI probe');
function commit(file, content = 'probe\n') {
  mkdirSync(dirname(join(repo, file)), { recursive: true });
  writeFileSync(join(repo, file), content);
  git('add', file);
  git('commit', '-qm', file);
  return git('rev-parse', 'HEAD');
}
const initial = commit('README.md');
git('checkout', '-qb', 'python-pr');
const pythonHead = commit('engine.py');
git('checkout', '-q', 'main');
const baseTip = commit('web/main-only.ts', 'unique frontend content\n');
git('checkout', '-qb', 'rename-out', baseTip);
mkdirSync(join(repo, 'app'));
git('mv', 'web/main-only.ts', 'app/main-only.ts');
git('commit', '-qm', 'move frontend path out of web');
const renameHead = git('rev-parse', 'HEAD');
function branch(name, file) {
  git('checkout', '-qb', name, initial);
  return commit(file);
}
const webHead = branch('web-pr', 'web/x.ts');
const contractHead = branch(
  'contract-pr',
  'docs/design/dashboard-api-v1-provisional.yaml',
);
const workflowHead = branch('workflow-pr', '.github/workflows/web.yml');
function run(
  event,
  base = baseTip,
  head = pythonHead,
  matcherStatus,
  missingRipgrep = false,
) {
  const output = join(scratch, 'output');
  writeFileSync(output, '');
  const bin = join(scratch, `bin-${matcherStatus ?? 'normal'}`);
  mkdirSync(bin, { recursive: true });
  // A runner without ripgrep must still detect frontend changes correctly.
  writeFileSync(
    join(bin, 'rg'),
    missingRipgrep ? '#!/bin/sh\nexit 127\n' : '#!/bin/sh\nexec grep -E "$@"\n',
    { mode: 0o755 },
  );
  if (matcherStatus !== undefined)
    writeFileSync(join(bin, 'grep'), `#!/bin/sh\nexit ${matcherStatus}\n`, {
      mode: 0o755,
    });
  const result = spawnSync('bash', ['-c', detector], {
    cwd: repo,
    encoding: 'utf8',
    env: {
      ...process.env,
      EVENT: event,
      BASE: base,
      HEAD: head,
      RUNNER_TEMP: scratch,
      GITHUB_OUTPUT: output,
      PATH: `${bin}:${process.env.PATH}`,
    },
  });
  return { ...result, output: readFileSync(output, 'utf8') };
}
after(() => rmSync(scratch, { recursive: true, force: true }));
describe('actual workflow change detector', () => {
  it('detects web, canonical contract and workflow changes without ripgrep', () => {
    for (const head of [webHead, contractHead, workflowHead]) {
      const result = run('pull_request', baseTip, head, undefined, true);
      assert.equal(result.status, 0, result.stderr);
      assert.equal(result.output, 'web=true\n');
    }
  });
  it('uses merge-base changes for behind-main PRs and merge groups', () => {
    for (const event of ['pull_request', 'merge_group']) {
      const result = run(event);
      assert.equal(result.status, 0, result.stderr);
      assert.equal(result.output, 'web=false\n');
    }
  });
  it('keeps direct push comparisons and detects old web paths on a rename', () => {
    for (const head of [pythonHead, renameHead]) {
      const result = run('push', baseTip, head);
      assert.equal(result.status, 0, result.stderr);
      assert.equal(result.output, 'web=true\n');
    }
  });
  it('fails closed on matcher errors or a missing matcher', () => {
    for (const status of [2, 127]) {
      const result = run('pull_request', baseTip, webHead, status);
      assert.equal(result.status, status);
      assert.equal(result.output, '');
      assert.match(result.stderr, /Frontend path matching failed/);
    }
  });
  it('fails closed on diff errors', () => {
    const result = run('pull_request', 'invalid-revision', webHead);
    assert.notEqual(result.status, 0);
    assert.equal(result.output, '');
  });
  it('runs checks for dispatch and absent initial push bases', () => {
    for (const [event, base] of [
      ['workflow_dispatch', baseTip],
      ['push', ''],
      ['push', '0'.repeat(40)],
    ]) {
      const result = run(event, base);
      assert.equal(result.status, 0, result.stderr);
      assert.equal(result.output, 'web=true\n');
    }
  });
});
