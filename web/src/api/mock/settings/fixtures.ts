import { executionResponse, indexResponse, type FieldValue, type SettingsCase, type SettingsExecution, type SettingsIndex, type SettingsSource } from './schema';
const unavailable = (code: string) => ({ state: 'UNSUPPORTED', reasons: [{ code, message: null }] });
const available = { state: 'AVAILABLE', reasons: [] };
function field(path: string, value?: string | number | boolean | null, extra: Partial<FieldValue> = {}): FieldValue {
  return { path, state: value === undefined ? 'ABSENT' : value === null ? 'NULL' : 'SET', ...(value !== undefined ? { value } : {}), class: 'operational', edit: 'F46.2', editable: false, ...extra };
}
export function settingsFixture(project: string, scenario: SettingsCase) {
  const envelope = { schema_version: '0.1.4' as const, project_id: project, control_revision: '1', generated_at: '2026-10-12T12:00:00Z' };
  const write = unavailable('AWAITS_F46_2');
  const document = { state: 'ADOPTED', in_force: true, digest: `sha256:${'a'.repeat(64)}`, on_disk_matches_adopted: true, write, violations: [], violations_truncated: false, yaml_error: null };
  const profile = (name: string | null, index: number, model: string | null) => ({
    name, index, fields: {
      harness: field(`/profiles/${name ?? '@' + index}/harness`, undefined, { effective: 'opencode', effective_source: 'policy' }),
      provider: field(`/profiles/${name ?? '@' + index}/provider`, 'example'), model: field(`/profiles/${name ?? '@' + index}/model`, model),
      effort: field(`/profiles/${name ?? '@' + index}/effort`, null), max_steps: field(`/profiles/${name ?? '@' + index}/max_steps`, 40),
      deadline_s: field(`/profiles/${name ?? '@' + index}/deadline_s`, 1200), description: field(`/profiles/${name ?? '@' + index}/description`, 'Synthetic investigation profile'),
    }, identity: model ? { catalog_id: `example/${model}`, provider: 'example', model, harness_ref: `example/${model}` } : null,
    identity_rule: 'adapter', identity_error: null, connection_id: 'conn-1111111111111111', routed_by: index === 0 ? ['default', 'archetype:implementer'] : ['archetype:reviewer'], routed_by_truncated: false,
  });
  const data: SettingsExecution['data'] = {
    document, configured: field('/configured', true), harness: field('/harness', 'opencode'), description: field('/description', 'Fictional read-only configuration'),
    profiles: [profile('standard', 0, 'model-a'), profile('review', 1, 'model-b')], profiles_truncated: false,
    routing: { default: field('/routing/default', 'standard'), classes: { entries: [], truncated: false },
      archetypes: { entries: [{ key: 'implementer', index: 0, profile: field('/routing/archetypes/implementer', 'standard') }, { key: 'reviewer', index: 1, profile: field('/routing/archetypes/reviewer', 'review') }], truncated: false }, cards: { entries: [], truncated: false }, resolution_order: ['card', 'class', 'archetype', 'default'] },
    connections: [{ connection_id: 'conn-1111111111111111', harness: 'opencode', provider: 'example', profiles: [0, 1], profiles_truncated: false,
      credential_sources: { provider_env: { scope: 'policy_wide', ref: '/provider_env' }, saved_login: 'NOT_SUPPLIED' }, endpoint: 'NOT_SUPPLIED', catalog: unavailable('AWAITS_F46_3') }], connections_truncated: false,
    provider_env: { state: field('/provider_env', 2, { class: 'legality_affecting' }), entries: [{ index: 0, name: 'EXAMPLE_PROVIDER_KEY', valid_name: true }, { index: 1, name: 'EXAMPLE_SECONDARY_KEY', valid_name: true }], entries_truncated: false },
    observed: { checked_in: 'dashboard_server_environment', caption: "the dashboard server's environment, not the environment runs launch from", provider_env: [{ index: 0, name: 'EXAMPLE_PROVIDER_KEY', present: true, problem: null }, { index: 1, name: 'EXAMPLE_SECONDARY_KEY', present: false, problem: 'unset' }], provider_env_truncated: false },
    controls: { steering: { mode: field('/steering/mode', 'walk', { class: 'legality_affecting', edit: 'later', allowed: ['crawl', 'walk', 'run'] }),
      envelope: { loop_deadline_s: field('/steering/envelope/loop_deadline_s', undefined, { effective: 3600, effective_source: 'default' }), max_auto_actions: field('/steering/envelope/max_auto_actions', undefined, { effective: 50, effective_source: 'default' }), repetition_n: field('/steering/envelope/repetition_n', undefined, { effective: 2, effective_source: 'default' }) }, effective: { mode: 'walk', source: 'default' } },
      containment: { mode: field('/containment/mode', 'required', { class: 'legality_affecting', edit: 'later', allowed: ['required', 'allow_weaker'] }), writable_count: 1, hide_count: 2, trusted_git_drivers_count: 0, effective: 'NOT_SUPPLIED' },
      switches: [{ path: '/recall/raw_history_search', value: field('/recall/raw_history_search', 'on', { edit: 'later', allowed: ['on', 'off'] }), default: 'off' }], notify: { configured: false, timeout_s: field('/notify/timeout_s'), max_output_bytes: field('/notify/max_output_bytes') } },
    pins_note: 'Existing invocation pins are unchanged.',
  };
  if (scenario === 'drifted') Object.assign(data.document, { state: 'DRIFTED', in_force: false, on_disk_matches_adopted: false });
  if (scenario === 'unpin') Object.assign(data.document, { state: 'UNPINNED', in_force: true, on_disk_matches_adopted: false });
  if (scenario === 'unknown') { data.document.state = 'FUTURE_DOCUMENT_STATE'; data.controls.steering.effective.source = 'future_source'; }
  if (scenario === 'withheld') {
    data.profiles[1] = profile(null, 1, null);
    data.profiles[1].fields.model = field('/profiles/@1/model', undefined, { state: 'SET', withheld: 'credential_shaped' });
    data.profiles[1].identity_error = { code: 'field_withheld', withheld_reason: 'credential_shaped', field_path: '/profiles/@1/model', suggestion: null, hint: 'Model identity is withheld.' };
    data.routing.cards.entries = [{ key: null, index: 0, profile: field('/routing/cards/@0', undefined, { state: 'SET', withheld: 'not_a_name' }) }];
    data.provider_env.entries.push({ index: 2, name: null, valid_name: false });
    data.provider_env.state.value = 3;
    data.observed.provider_env.push({ index: 2, name: null, present: false, problem: 'aew_variable' });
  }
  if (scenario === 'partial') {
    data.profiles_truncated = data.connections_truncated = data.provider_env.entries_truncated = data.observed.provider_env_truncated = true;
    data.profiles[0].routed_by_truncated = data.connections[0].profiles_truncated = data.routing.archetypes.truncated = true;
    data.connections[0].profiles.push(5); data.profiles[1].connection_id = 'conn-2222222222222222';
  }
  if (scenario === 'long') {
    data.description.value = '<script>window.__settingsHostile=1</script> ' + 'Long supplied description '.repeat(15);
    data.profiles[0].name = 'profile-' + 'long-name-'.repeat(22);
    data.profiles[0].fields.description.value = 'A long profile description '.repeat(18);
  }
  if (['manifest', 'invalid', 'absent', 'empty'].includes(scenario)) {
    data.profiles = []; data.connections = []; data.routing.archetypes.entries = [];
    if (scenario !== 'empty') {
      Object.assign(data.document, { state: scenario === 'manifest' ? 'MANIFEST_DRIFTED' : scenario === 'invalid' ? 'INVALID' : 'ABSENT', in_force: scenario === 'absent', on_disk_matches_adopted: false });
      data.configured = field('/configured'); data.harness = field('/harness'); data.description = field('/description'); data.routing.default = field('/routing/default');
      data.provider_env.entries = []; data.observed.provider_env = [];
      data.provider_env.state = field('/provider_env');
      data.controls.steering.mode = field('/steering/mode');
    }
    if (scenario === 'invalid') { data.document.violations = [{ path: '/profiles/@0/model', code: 'type', expected: 'string', extra_key: null }]; data.document.yaml_error = { code: 'YAML_SYNTAX', line: null, column: null }; }
  }
  const documents: SettingsIndex['data']['documents'] = ['project', 'execution', 'gates', 'guardrails', 'checks', 'pricing'].map((name, index) => ({ document: name, index, same_file_as: null, supported: name === 'execution' ? available : unavailable('AWAITS_LATER_F46'), state: name === 'execution' ? data.document.state : 'ADOPTED', in_force: name === 'execution' ? data.document.in_force : true, digest: name === 'execution' ? data.document.digest : `sha256:${'b'.repeat(64)}`, write }));
  if (scenario === 'manifest') documents.forEach(doc => { doc.state = 'MANIFEST_DRIFTED'; doc.in_force = false; });
  if (scenario === 'partial') documents[5].same_file_as = 2;
  data.profiles.sort((a, b) => (a.name ?? '').localeCompare(b.name ?? '') || a.index - b.index);
  return { index: indexResponse.parse({ ...envelope, data: { manifest: { state: scenario === 'manifest' ? 'DRIFTED' : 'ADOPTED' }, activities: ['execution', 'providers', 'workflow', 'project'].map(activity => ({ activity, capability: ['execution', 'providers'].includes(activity) ? available : unavailable('AWAITS_LATER_F46') })), documents, documents_truncated: scenario === 'partial' } }), execution: executionResponse.parse({ ...envelope, data }) };
}
// The page depends on this read interface, not fixture storage or HTTP routes.
// F1c can supply an authenticated transport only after contract adoption.
export const fixtureSettingsSource: SettingsSource = {
  async readIndex(project, scenario, signal) { signal.throwIfAborted(); if (scenario === 'error') throw new Error('Synthetic configuration read failed.'); return settingsFixture(project, scenario).index; },
  async readExecution(project, scenario, signal) { signal.throwIfAborted(); return settingsFixture(project, scenario).execution; },
};
