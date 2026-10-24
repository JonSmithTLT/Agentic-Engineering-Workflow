import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useDashboard } from '../../../client/dashboard';
import { useReadSession } from '../../../client/queries';
import { InvestigationTabs, focusBelowHeader } from '../../../components/InvestigationTabs';
import { SemanticValue } from '../../../components/States';
import { CopyDashboardLink } from '../../../components/CopyDashboardLink';
import { fixtureSettingsSource } from './fixtures';
import { executionResponse, indexResponse, settingsCases, type FieldValue, type SettingsExecution, type SettingsIndex, type SettingsSource, type SettingsCase } from './schema';
import './settings.css';
const activities = ['execution', 'providers', 'workflow', 'project'];
const sections = ['profiles', 'routing', 'controls'];
const states = ['MANIFEST_DRIFTED', 'DRIFTED', 'INVALID', 'ADOPTED', 'UNPINNED', 'ABSENT'];
const capabilityStates = ['AVAILABLE', 'UNAVAILABLE', 'UNSUPPORTED', 'UNKNOWN'];
const sourceIds = new WeakMap<SettingsSource, number>();
let nextSourceId = 0;
function sourceIdentity(source: SettingsSource) {
  let identity = sourceIds.get(source);
  if (identity === undefined) { identity = ++nextSourceId; sourceIds.set(source, identity); }
  return identity;
}
const label = (value: string) => value.replaceAll('_', ' ');
const scalar = (value: unknown) => value === null ? 'null' : String(value);
function Facts({ children }: { children: ReactNode }) { return <dl className="settings-facts">{children}</dl>; }
function Fact({ title, children }: { title: string; children: ReactNode }) { return <div><dt>{title}</dt><dd>{children}</dd></div>; }
function Truncated({ yes, name }: { yes: boolean; name: string }) { return yes ? <p className="preview-note">{name} is truncated. Additional entries are not listed.</p> : null; }
function Capability({ value }: { value: SettingsExecution['data']['document']['write'] }) {
  return <><SemanticValue value={value.state} known={capabilityStates} />{value.reasons.map((reason, index) => <p key={index}><code>{reason.code}</code>{reason.message !== null && <> — {reason.message}</>}</p>)}</>;
}
export function ConfiguredField({ name, value }: { name: string; value: FieldValue }) {
  return <div className="settings-field"><h4>{name}</h4><Facts>
    <Fact title="Configured">{value.withheld !== undefined ? <>Withheld · <SemanticValue value={value.withheld} known={['not_a_model_id', 'not_a_name', 'not_a_harness_name', 'credential_shaped']} /></> : value.state === 'ABSENT' ? 'Not configured (ABSENT)' : value.state === 'NULL' ? 'Configured null (NULL)' : <code>{scalar(value.value)}</code>}</Fact>
    {Object.hasOwn(value, 'effective') && <Fact title="Supplied effective"><code>{scalar(value.effective)}</code>{value.effective_source && <> · <SemanticValue value={value.effective_source} known={['profile', 'policy', 'default']} /></>}</Fact>}
    <Fact title="Classification"><SemanticValue value={value.class} known={['operational', 'legality_affecting']} /></Fact>
  </Facts>{value.description && <p>{value.description}</p>}<details><summary>Field definition</summary><Facts>
    <Fact title="Display locator"><code>{value.path}</code>{value.path.split('/').some(part => /^@\d+$/.test(part)) && <p>Masked locator; valid only under this document digest. Not an edit target or persistent JSON Pointer identity.</p>}</Fact>
    <Fact title="Edit scope"><SemanticValue value={value.edit} known={['F46.2', 'later', 'never']} /></Fact>
    <Fact title="Editable">{String(value.editable)}</Fact>
    {value.allowed && <Fact title="Allowed values">{value.allowed.map(item => <code key={item}>{item} </code>)}</Fact>}
  </Facts></details></div>;
}
function DocumentBanner({ doc }: { doc: SettingsExecution['data']['document'] }) {
  const message = doc.state === 'MANIFEST_DRIFTED' ? 'Manifest drifted. Policy paths cannot be trusted; configuration values are unavailable.' : doc.state === 'DRIFTED' ? 'On-disk configuration is drifted and not in force. This view does not reconstruct adopted values.' : doc.state === 'UNPINNED' ? 'Never adopted. The supplied values are in force but have not been pinned.' : doc.state === 'INVALID' ? 'Configuration is invalid and not in force. Only supplied validation information is available.' : doc.state === 'ABSENT' ? 'Configuration is absent. In force describes the supplied unconfigured state.' : undefined;
  return <>{message && <p className="preview-note" role="status">{message}</p>}<Facts><Fact title="Document state"><SemanticValue value={doc.state} known={states} /></Fact><Fact title="In force">{String(doc.in_force)}</Fact><Fact title="On disk matches adopted">{String(doc.on_disk_matches_adopted)}</Fact><Fact title="Configuration digest"><code>{doc.digest}</code></Fact><Fact title="Read-only · write capability"><Capability value={doc.write} /></Fact></Facts>
    {doc.violations.length > 0 && <section aria-label="Validation problems"><h3>Validation problems</h3><ul>{doc.violations.map((v, i) => <li key={i}><code>{v.path}</code> · <code>{v.code}</code>{v.expected !== null && <> · Expected: {v.expected}</>}{v.extra_key !== null && <> · Extra key: <code>{v.extra_key}</code></>}</li>)}</ul></section>}
    <Truncated yes={doc.violations_truncated} name="Validation problem list" />
    {doc.yaml_error && <p>YAML syntax error · Line {doc.yaml_error.line ?? 'not supplied'}, column {doc.yaml_error.column ?? 'not supplied'}.</p>}
  </>;
}
export default function SettingsPage({ source = fixtureSettingsSource }: { source?: SettingsSource }) {
  const { project } = useDashboard();
  const session = useReadSession();
  const [params, setParams] = useSearchParams();
  const activity = params.get('settings_activity') ?? 'execution';
  const section = params.get('settings_section') ?? 'profiles';
  const scenario = params.get('settings_case') ?? 'adopted';
  const selection = params.get('settings_profile');
  const selectedDigest = params.get('settings_digest');
  const invalid = !activities.includes(activity) || !sections.includes(section) || !settingsCases.includes(scenario as SettingsCase) || ['settings_activity', 'settings_section', 'settings_case', 'settings_profile', 'settings_digest'].some(key => params.getAll(key).length > 1) || (selection !== null && (!/^(0|[1-9]\d*)$/.test(selection) || selectedDigest === null)) || (selectedDigest !== null && !/^sha256:[0-9a-f]{64}$/.test(selectedDigest));
  const [result, setResult] = useState<{ key: string; index?: SettingsIndex; execution?: SettingsExecution; error?: string }>({ key: '' });
  const [retry, setRetry] = useState(0);
  const projectId = project.data?.value.project_id;
  const key = JSON.stringify([sourceIdentity(source), projectId, session.generation, scenario, retry, activity]);
  const current = result.key === key ? result : undefined;
  const heading = useRef<HTMLHeadingElement>(null);
  const pendingFocus = useRef(false);
  useEffect(() => {
    if (invalid || !projectId) return;
    const controller = new AbortController();
    let retired = false;
    void (async () => {
      try {
        if (scenario === 'loading') await new Promise<void>(resolve => { const timer = window.setTimeout(resolve, 1500); controller.signal.addEventListener('abort', () => { window.clearTimeout(timer); resolve(); }, { once: true }); });
        controller.signal.throwIfAborted();
        const rawIndex = await source.readIndex(projectId, scenario as SettingsCase, controller.signal);
        if (retired || controller.signal.aborted) return;
        const index = indexResponse.parse(rawIndex);
        if (index.project_id !== projectId) throw new Error('Configuration project binding mismatch.');
        if (!['execution', 'providers'].includes(activity)) { if (!retired) setResult({ key, index }); return; }
        if (index.data.activities.find(item => item.activity === activity)?.capability.state !== 'AVAILABLE') { if (!retired) setResult({ key, index }); return; }
        const rawExecution = await source.readExecution(projectId, scenario as SettingsCase, controller.signal);
        if (retired || controller.signal.aborted) return;
        const execution = executionResponse.parse(rawExecution);
        const doc = index.data.documents.find(item => item.document === 'execution');
        if (execution.project_id !== projectId || !doc || doc.digest !== execution.data.document.digest || doc.state !== execution.data.document.state || doc.in_force !== execution.data.document.in_force) throw new Error('Configuration document binding mismatch.');
        if (!retired) setResult({ key, index, execution });
      } catch (error) { if (!retired) setResult({ key, error: error instanceof Error ? error.message : 'Configuration read failed.' }); }
    })();
    return () => { retired = true; controller.abort(); };
  }, [key, invalid, projectId, scenario, source, activity]);
  const data = current?.execution?.data;
  const selected = selectedDigest === data?.document.digest
    ? data?.profiles.find(profile => String(profile.index) === selection)
    : undefined;
  useEffect(() => { if (pendingFocus.current && selected) { pendingFocus.current = false; focusBelowHeader(heading.current); } }, [selection, selected]);
  function change(name: string, value: string) {
    setParams(previous => { const next = new URLSearchParams(previous); next.set(name, value); if (name === 'settings_case') { next.delete('settings_profile'); next.delete('settings_digest'); } return next; });
  }
  const title = <><h1>Settings</h1><p className="preview-note">Settings fixture preview · proposed API 0.1.4 · Synthetic data. No live configuration reads or writes.</p></>;
  if (invalid) return <>{title}<div role="alert" className="empty">Unsupported Settings presentation link. No configuration data was read.</div></>;
  const tabs = <InvestigationTabs label="Settings activities" prefix="settings" tabs={activities.map(id => ({ id, label: label(id[0].toUpperCase() + id.slice(1)) }))} active={activity} select={id => change('settings_activity', id)} />;
  return <div className="settings-page">{title}<div className="settings-toolbar"><label>Settings scenario <select value={scenario} onChange={event => change('settings_case', event.target.value)}>{settingsCases.map(value => <option key={value}>{value}</option>)}</select></label><CopyDashboardLink /></div>{tabs}
    {!projectId || !current ? <p role="status">Loading configuration fixture…</p> : current.error ? <div className="empty" role="alert"><h2>Could not load Settings</h2><p>{current.error}</p><button onClick={() => setRetry(value => value + 1)}>Retry configuration</button></div> : !data && current.index ? <section className="panel settings-panel" id={`settings-panel-${activity}`} role="tabpanel" aria-labelledby={`settings-tab-${activity}`}><h2>{label(activity[0].toUpperCase() + activity.slice(1))}</h2>{current.index.data.activities.find(item => item.activity === activity) ? <Capability value={current.index.data.activities.find(item => item.activity === activity)!.capability} /> : <p>Activity capability not supplied.</p>}<p>This activity's configuration detail is not supplied in F46.1.</p></section> : data && current.index && <>
      <section className="panel settings-panel"><h2>Execution policy identity</h2><DocumentBanner doc={data.document} />{data.description.state === 'SET' && !data.description.withheld && <p>{scalar(data.description.value)}</p>}</section>
      <div id={`settings-panel-${activity}`} role="tabpanel" aria-labelledby={`settings-tab-${activity}`}>
        {['workflow', 'project'].includes(activity) ? <section className="panel settings-panel"><h2>{label(activity[0].toUpperCase() + activity.slice(1))}</h2><Capability value={current.index.data.activities.find(item => item.activity === activity)!.capability} /><p>This editor is not supplied in F46.1.</p></section> : activity === 'providers' ? <Providers data={data} /> : <>
          <InvestigationTabs label="Execution sections" prefix="settings-execution" tabs={sections.map(id => ({ id, label: label(id[0].toUpperCase() + id.slice(1)) }))} active={section} select={id => change('settings_section', id)} />
          <div id={`settings-execution-panel-${section}`} role="tabpanel" aria-labelledby={`settings-execution-tab-${section}`}>
            {['MANIFEST_DRIFTED', 'INVALID', 'ABSENT'].includes(data.document.state) ? <p className="empty">No execution values supplied for this document state.</p> : section === 'profiles' ? <>
              <section className="panel settings-panel"><h2>Profiles</h2><Truncated yes={data.profiles_truncated} name="Profile list" />{data.profiles.length === 0 ? <p>No profiles supplied.</p> : <div className="table-scroll settings-profile-scroll"><table><thead><tr><th>Profile</th><th>Provider / model</th><th>Harness</th><th>Used by</th></tr></thead><tbody>{data.profiles.map(profile => <tr key={profile.index}><td><button aria-pressed={selected?.index === profile.index} onClick={() => { pendingFocus.current = window.innerWidth < 1024; setParams(previous => { const next = new URLSearchParams(previous); next.set('settings_profile', String(profile.index)); next.set('settings_digest', data.document.digest); return next; }); }}>{profile.name ?? `Profile ${profile.index} (name withheld)`}</button></td><td>{profile.identity ? <code>{profile.identity.catalog_id}</code> : 'Identity not supplied'}</td><td>{Object.hasOwn(profile.fields.harness, 'effective') ? scalar(profile.fields.harness.effective) : profile.fields.harness.withheld ? 'Withheld' : profile.fields.harness.state === 'SET' ? scalar(profile.fields.harness.value) : 'Not configured'}</td><td>{profile.routed_by.length ? profile.routed_by.join(', ') : 'No routing references supplied'}<Truncated yes={profile.routed_by_truncated} name="Routing references" /></td></tr>)}</tbody></table></div>}</section>
              {selection !== null && (selectedDigest !== data.document.digest ? <p role="alert">Selected profile belongs to a different document digest. Select a profile from this document.</p> : !selected ? <p role="status">Selected profile is not listed in this projection; absence does not establish unavailability.</p> : <section className="panel settings-panel"><h2 ref={heading} tabIndex={-1}>Profile {selected.name ?? `${selected.index} (name withheld)`}</h2><p>Read-only field inspection. Editing awaits F46.2.</p>{selected.identity_error && <p className="preview-note">Identity error: <SemanticValue value={selected.identity_error.code} known={['model_id_malformed', 'model_id_no_provider', 'model_id_provider_conflict', 'field_withheld']} /> · <code>{selected.identity_error.field_path}</code> · {selected.identity_error.hint}{selected.identity_error.suggestion !== null && <> · Suggestion: {selected.identity_error.suggestion}</>}</p>}<Facts><Fact title="Identity rule"><SemanticValue value={selected.identity_rule} known={['adapter', 'inherited']} /></Fact><Fact title="Provider connection">{selected.connection_id === null ? 'Not supplied' : <><code>{selected.connection_id}</code>{!data.connections.some(item => item.connection_id === selected.connection_id) && <p>Connection is not listed in this projection.</p>}</>}</Fact>{selected.identity && <><Fact title="Catalog identity"><code>{selected.identity.catalog_id}</code></Fact><Fact title="Harness reference"><code>{selected.identity.harness_ref}</code></Fact></>}</Facts><div className="settings-fields">{Object.entries(selected.fields).map(([name, value]) => <ConfiguredField key={name} name={label(name)} value={value} />)}</div></section>)}
            </> : section === 'routing' ? <section className="panel settings-panel"><h2>Routing</h2><p>Supplied resolution order: {data.routing.resolution_order.join(' → ')}</p><ConfiguredField name="Default profile" value={data.routing.default} />{(['classes', 'archetypes', 'cards'] as const).map(name => <section key={name}><h3>{label(name)}</h3><Truncated yes={data.routing[name].truncated} name={`${name} routes`} />{data.routing[name].entries.length === 0 ? <p>No {name} overrides supplied.</p> : data.routing[name].entries.map(entry => <ConfiguredField key={entry.index} name={entry.key ?? `Route ${entry.index} (key withheld)`} value={entry.profile} />)}</section>)}</section> : <Controls data={data} />}
          </div>
        </>}
      </div>
      <details><summary>Document inventory and response metadata</summary><p>Manifest: <SemanticValue value={current.index.data.manifest.state} known={['ADOPTED', 'DRIFTED']} /></p><Truncated yes={current.index.data.documents_truncated} name="Document inventory" /><div className="table-scroll"><table><thead><tr><th>Document</th><th>State</th><th>In force</th><th>Supported</th><th>Write</th></tr></thead><tbody>{current.index.data.documents.map(doc => <tr key={doc.index}><td>{doc.document ?? `Policy document ${doc.index} (name withheld)`}{doc.same_file_as !== null && <p>Same file as document index {doc.same_file_as}.</p>}<details><summary>Document digest</summary><code>{doc.digest}</code></details></td><td><SemanticValue value={doc.state} known={states} /></td><td>{String(doc.in_force)}</td><td><Capability value={doc.supported} /></td><td><Capability value={doc.write} /></td></tr>)}</tbody></table></div><Facts><Fact title="Project">{current.index.project_id}</Fact><Fact title="Inventory control revision">{current.index.control_revision}</Fact><Fact title="Inventory generated UTC">{current.index.generated_at}</Fact><Fact title="Execution control revision">{current.execution!.control_revision}</Fact><Fact title="Execution generated UTC">{current.execution!.generated_at}</Fact></Facts></details><p className="muted">{data.pins_note}</p>
    </>}
  </div>;
}
function Controls({ data }: { data: SettingsExecution['data'] }) {
  const controls = data.controls;
  return <section className="panel settings-panel"><h2>Controls</h2><ConfiguredField name="Configured execution" value={data.configured} /><ConfiguredField name="Harness" value={data.harness} /><h3>Steering</h3><ConfiguredField name="Steering mode" value={controls.steering.mode} /><Facts><Fact title="Supplied effective mode">{controls.steering.effective.mode ?? 'Not supplied'}</Fact><Fact title="Effective source"><SemanticValue value={controls.steering.effective.source} known={['raise', 'lower', 'default', 'none']} /></Fact></Facts><div className="settings-fields">{Object.entries(controls.steering.envelope).map(([name, value]) => <ConfiguredField key={name} name={label(name)} value={value} />)}</div><h3>Containment</h3><ConfiguredField name="Containment mode" value={controls.containment.mode} /><Facts><Fact title="Writable entries">{controls.containment.writable_count}</Fact><Fact title="Hidden entries">{controls.containment.hide_count}</Fact><Fact title="Trusted Git drivers">{controls.containment.trusted_git_drivers_count}</Fact><Fact title="Effective containment">Not supplied. Configuration does not establish active or tested containment.</Fact></Facts><h3>Switches</h3>{controls.switches.map(item => <div key={item.path}><ConfiguredField name={item.path} value={item.value} /><p>Supplied default: <code>{item.default}</code></p></div>)}<h3>Notifications</h3><p>Configured: {String(controls.notify.configured)}. Executable arguments are not supplied.</p><ConfiguredField name="Timeout (seconds)" value={controls.notify.timeout_s} /><ConfiguredField name="Maximum output (bytes)" value={controls.notify.max_output_bytes} /></section>;
}
function Providers({ data }: { data: SettingsExecution['data'] }) {
  return <section className="panel settings-panel"><h2>Provider connections</h2><Truncated yes={data.connections_truncated} name="Connection list" />{data.connections.length === 0 && <p>No connections supplied.</p>}{data.connections.map(connection => <section className="settings-field" key={connection.connection_id}><h3>{connection.provider} · {connection.harness}</h3><Facts><Fact title="Connection identity"><code>{connection.connection_id}</code></Fact><Fact title="Profiles">{connection.profiles.length ? connection.profiles.map(index => data.profiles.find(profile => profile.index === index)?.name ?? `Profile ${index} (name not listed)`).join(', ') : 'No profile references supplied'}<Truncated yes={connection.profiles_truncated} name="Connection profile references" /></Fact><Fact title="Endpoint">Not supplied · awaits F46.3</Fact><Fact title="Model catalog"><Capability value={connection.catalog} /></Fact><Fact title="Saved login">Not supplied</Fact><Fact title="Credential-source association">Named by the policy (not per provider) · <code>{connection.credential_sources.provider_env.ref}</code></Fact></Facts></section>)}<h3>Policy-wide credential sources</h3><p>Names and presence only. Presence does not establish provider access or launch-environment availability.</p><ConfiguredField name="Provider environment configuration" value={data.provider_env.state} /><p>Presence checked in: <SemanticValue value={data.observed.checked_in} known={['dashboard_server_environment', 'cli_environment']} /> · {data.observed.caption}</p><Truncated yes={data.provider_env.entries_truncated} name="Credential-source names" /><Truncated yes={data.observed.provider_env_truncated} name="Presence observations" />{data.provider_env.entries.length === 0 ? <p>No credential-source names supplied.</p> : <div className="table-scroll"><table><thead><tr><th>Policy name</th><th>Valid name</th><th>Observed presence</th><th>Problem</th></tr></thead><tbody>{data.provider_env.entries.map(entry => { const observed = data.observed.provider_env.find(value => value.index === entry.index); return <tr key={entry.index}><td>{entry.name ?? `Invalid or withheld entry at provider_env[${entry.index}]`}</td><td>{String(entry.valid_name)}</td><td>{observed ? String(observed.present) : 'Not supplied'}</td><td>{observed ? observed.problem === null ? 'No problem reported' : <SemanticValue value={observed.problem} known={['unset', 'aew_variable', 'holds_aew_credential']} /> : 'Not supplied'}</td></tr>; })}</tbody></table></div>}</section>;
}
