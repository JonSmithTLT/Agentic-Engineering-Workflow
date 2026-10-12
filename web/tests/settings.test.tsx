import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import SettingsPage, { ConfiguredField } from '../src/api/mock/settings/Settings';
import { fieldValue, settingsCases, type SettingsSource } from '../src/api/mock/settings/schema';
import { fixtureSettingsSource, settingsFixture } from '../src/api/mock/settings/fixtures';
vi.mock('../src/client/dashboard', () => ({ useDashboard: () => ({ project: { data: { value: { project_id: 'synthetic-settings' } } } }) }));
vi.mock('../src/client/queries', () => ({ useReadSession: () => ({ generation: 1 }) }));
beforeEach(() => { vi.restoreAllMocks(); });
function mount(query = '', source?: SettingsSource) { return render(<MemoryRouter initialEntries={['/settings' + query]}><SettingsPage source={source} /></MemoryRouter>); }
it('validates every synthetic Appendix A case without modifying accepted contracts', () => {
  for (const scenario of settingsCases) expect(settingsFixture('synthetic-settings', scenario).execution.schema_version).toBe('0.1.4');
});
it('enforces SET/withheld/NULL/ABSENT presence and refuses extra fields and edits', () => {
  const original = settingsFixture('synthetic-settings', 'adopted').execution.data.configured;
  expect(fieldValue.safeParse({ ...original, state: 'ABSENT' }).success).toBe(false);
  expect(fieldValue.safeParse({ ...original, state: 'NULL', value: null }).success).toBe(true);
  expect(fieldValue.safeParse({ ...original, withheld: 'credential_shaped', value: null }).success).toBe(false);
  expect(fieldValue.safeParse({ ...original, editable: true }).success).toBe(false);
  expect(fieldValue.safeParse({ ...original, credential: 'never-supplied' }).success).toBe(false);
  expect(fieldValue.safeParse({ ...original, path: '' }).success).toBe(true);
});
it('keeps configured null, absent effective and withheld values visibly distinct', () => {
  const fixture = settingsFixture('synthetic-settings', 'withheld').execution.data;
  render(<><ConfiguredField name="Null effort" value={fixture.profiles[0].fields.effort} /><ConfiguredField name="Default deadline" value={fixture.controls.steering.envelope.loop_deadline_s} /><ConfiguredField name="Withheld model" value={fixture.profiles.find(profile => profile.index === 1)!.fields.model} /></>);
  expect(screen.getByText('Configured null (NULL)')).toBeDefined();
  expect(screen.getByText('Not configured (ABSENT)')).toBeDefined();
  expect(screen.getByText('3600')).toBeDefined();
  expect(screen.getByText('credential shaped')).toBeDefined();
});
it('opens a read-only profile and preserves desktop row focus', async () => {
  mount(); const pick = await screen.findByRole('button', { name: 'standard' }); pick.focus(); fireEvent.click(pick);
  await screen.findByRole('heading', { name: 'Profile standard' });
  expect(document.activeElement).toBe(pick);
  expect(screen.queryByRole('button', { name: /^Save/ })).toBeNull();
  expect(screen.queryByRole('textbox')).toBeNull();
});
it('masked profile locators are digest-bound and not reusable from a different digest', async () => {
  mount(`?settings_case=withheld&settings_profile=1&settings_digest=sha256:${'b'.repeat(64)}`);
  await screen.findByText('Selected profile belongs to a different document digest. Select a profile from this document.');
  expect(screen.queryByRole('heading', { name: 'Profile 1 (name withheld)' })).toBeNull();
});
it('exposes masked locator warning and supplied identity error', async () => {
  mount('?settings_case=withheld'); fireEvent.click(await screen.findByRole('button', { name: 'Profile 1 (name withheld)' }));
  await screen.findByRole('heading', { name: 'Profile 1 (name withheld)' });
  expect(screen.getByText('field withheld')).toBeDefined();
  expect(screen.getAllByText(/Masked locator; valid only/).length).toBeGreaterThan(0);
});
it.each([['drifted', /On-disk configuration is drifted/], ['unpin', /Never adopted/], ['manifest', /Manifest drifted/], ['invalid', /Configuration is invalid/], ['absent', /Configuration is absent/]])('shows supplied state banner for %s', async (scenario, text) => {
  mount(`?settings_case=${scenario}`); await screen.findByText(text);
});
it('names credential observation context without implying per-provider authentication', async () => {
  mount('?settings_activity=providers'); await screen.findByRole('heading', { name: 'Provider connections' });
  expect(screen.getByText(/Named by the policy \(not per provider\)/)).toBeDefined();
  expect(screen.getByText(/the dashboard server's environment/)).toBeDefined();
  expect(screen.getByText('EXAMPLE_PROVIDER_KEY')).toBeDefined();
  expect(screen.queryByRole('button', { name: /models/i })).toBeNull();
});
it('keeps unsupported activities explicit and tab keyboard focus on the new tab', async () => {
  mount(); await screen.findByRole('button', { name: 'standard' });
  const tab = screen.getByRole('tab', { name: 'Execution' }); tab.focus(); fireEvent.keyDown(tab, { key: 'End' });
  await screen.findByRole('heading', { name: 'Project' });
  expect(document.activeElement).toBe(screen.getByRole('tab', { name: 'Project' }));
  expect(screen.getAllByText('AWAITS_LATER_F46').length).toBeGreaterThan(0);
});
it('rejects invalid and repeated links before reading configuration', async () => {
  const source = { readIndex: vi.fn(), readExecution: vi.fn() };
  mount('?settings_case=adopted&settings_case=withheld', source);
  await screen.findByText(/Unsupported Settings presentation link/);
  expect(source.readIndex).not.toHaveBeenCalled();
});
it('rejects source/project mismatch instead of displaying replacement data', async () => {
  const source: SettingsSource = { ...fixtureSettingsSource, async readIndex() { return settingsFixture('another-project', 'adopted').index; } };
  mount('', source); await screen.findByText('Configuration project binding mismatch.');
  expect(screen.queryByRole('button', { name: 'standard' })).toBeNull();
});
it('does not read concealed execution details for an unsupported activity', async () => {
  const source = { ...fixtureSettingsSource, readExecution: vi.fn(fixtureSettingsSource.readExecution) };
  mount('?settings_activity=workflow', source);
  await screen.findByRole('heading', { name: 'Workflow' });
  expect(source.readExecution).not.toHaveBeenCalled();
});
it('late scenario reads cannot replace the active scenario', async () => {
  let release!: (value: unknown) => void;
  const source: SettingsSource = { ...fixtureSettingsSource, readIndex: vi.fn(async (project, scenario) => scenario === 'adopted' ? await new Promise(resolve => { release = resolve; }) : settingsFixture(project, scenario).index) };
  mount('', source); await waitFor(() => expect(release).toBeDefined());
  fireEvent.change(screen.getByLabelText('Settings scenario'), { target: { value: 'drifted' } });
  await screen.findByText(/On-disk configuration is drifted/);
  release(settingsFixture('synthetic-settings', 'adopted').index);
  await waitFor(() => expect(screen.getByText(/On-disk configuration is drifted/)).toBeDefined());
});
it('contains unknown semantics and hostile descriptions as plain data', async () => {
  mount('?settings_case=long'); await screen.findByText(/<script>window.__settingsHostile=1<\/script>/);
  expect(document.querySelector('.settings-page script')).toBeNull();
});
it('reports empty and truncated projections explicitly', async () => {
  mount('?settings_case=partial&settings_activity=providers'); await screen.findByText('Connection list is truncated. Additional entries are not listed.');
  expect(screen.getByText(/Profile 5 \(name not listed\)/)).toBeDefined();
});
