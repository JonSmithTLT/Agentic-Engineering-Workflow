import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Timestamp } from '../api/additive-schema';
import { historySearchRoute } from '../api/maps-history';
import { historyKinds, trustSources } from '../api/vocabulary';
import { navigationParams } from '../api/navigation';
import { readOnlyHistoryArgv } from '../api/cli';
import { CapabilityGate, useDashboard } from '../client/dashboard';
import { useHistorySearch, type SearchDraft } from '../client/history-search';
import { Reasons } from '../components/ProjectionViews';
import { SemanticValue } from '../components/States';
import { SourceStrip } from '../components/Investigation';
import { CopyCli } from '../components/CopyCli';
import { CopyDashboardLink } from '../components/CopyDashboardLink';
import { EntityAnchor } from '../components/EntityAnchor';
import { focusBelowHeader } from '../components/InvestigationTabs';
import { rememberReference, restoreReference, returnPosition } from '../components/reference-return';

export function HistorySearchPage() {
  const { project, caps, capabilities } = useDashboard();
  const location = useLocation();
  const permitted = !!project.data && caps?.history_search?.state === 'AVAILABLE';
  const { state, session } = useHistorySearch(permitted);
  const { draft, result, pending, error } = state;
  const [errors, setErrors] = useState<Record<string, string>>({});
  const composing = useRef(false);
  const form = useRef<HTMLFormElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const restored = useRef(false);
  const focusAfterClear = useRef(false);
  const data = result?.value.data;
  useEffect(() => {
    if (!focusAfterClear.current || pending) return;
    form.current?.querySelector<HTMLInputElement>('#search-term-0')?.focus();
    focusAfterClear.current = false;
  }, [draft, pending]);
  useEffect(() => {
    document.title = 'Raw history search · AEW';
    const position = returnPosition(location.state);
    if (!position) focusBelowHeader(heading.current!);
  }, [location.key, location.state]);
  useEffect(() => {
    if (restored.current || !data) return;
    const position = returnPosition(location.state);
    if (!position) return;
    const row = [...document.querySelectorAll<HTMLElement>('[data-search-hit]')]
      .find(element => element.dataset.searchHit === position.reference);
    const anchor = row?.querySelector<HTMLAnchorElement>('a');
    if (anchor) { restoreReference(position, anchor); restored.current = true; }
  }, [data, location.state]);
  const update = (value: Partial<SearchDraft>) => session.edit({ ...draft, ...value });
  function clear() {
    focusAfterClear.current = true;
    session.clear();
    setErrors({});
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (composing.current || pending) return;
    const nextErrors: Record<string, string> = {};
    draft.terms.forEach((term, index) => {
      if (!term.trim() || /\p{Cc}/u.test(term)) nextErrors[`search-term-${index}`] = 'Enter a literal term without control characters.';
    });
    for (const field of ['since', 'until'] as const) {
      if (draft[field] && !Timestamp.safeParse(draft[field]).success)
        nextErrors[`search-${field}`] = 'Use a UTC timestamp with seconds, such as 2026-10-10T00:00:00Z.';
    }
    if (!nextErrors['search-since'] && !nextErrors['search-until'] && draft.since && draft.until && Date.parse(draft.since) > Date.parse(draft.until))
      nextErrors['search-until'] = 'Until must be at or after Since.';
    const query = { terms: [...draft.terms], kinds: [...draft.kinds], since: draft.since || undefined, until: draft.until || undefined, limit: draft.limit };
    if (!Object.keys(nextErrors).length) {
      try { historySearchRoute(query); }
      catch { nextErrors['search-term-0'] = 'Use up to 16 terms, 512 characters including separators, and an encoded query within 2 KiB.'; }
    }
    setErrors(nextErrors);
    const first = Object.keys(nextErrors)[0];
    if (first) { document.getElementById(first)?.focus(); return; }
    void session.submit(query);
  }
  const description = (id: string) => errors[id] ? `${id}-error` : undefined;
  const params = navigationParams(new URLSearchParams(location.search));
  const historyHref = '/history' + (params.size ? '?' + params : '');
  return <section className="history-search-page">
    <div className="panel-heading">
      <h1 tabIndex={-1} ref={heading}>Raw history search</h1>
      <Link to={historyHref}>Back to History</Link>
      <CopyDashboardLink />
    </div>
    <p className="preview-note">Raw history (not admitted Knowledge). Historical references do not establish current truth or evaluated benefit.</p>
    {!caps?.history_search ?
      (!caps ? <CapabilityGate name="history_search"><span /></CapabilityGate> : <p role="status">Raw history search is not offered on this project.</p>) :
      <CapabilityGate name="history_search">
        <form className="panel history-search-form" noValidate ref={form} onSubmit={submit}>
          <fieldset disabled={pending}>
            <legend>Literal search terms</legend>
            <p id="search-term-help">Each term is a literal phrase; all terms must match. Search runs only when you select Search. Terms stay in this browser session and are not saved in links.</p>
            {draft.terms.map((term, index) => <div className="search-term-row" key={index}>
              <label htmlFor={`search-term-${index}`}>Term {index + 1}</label>
              <input id={`search-term-${index}`} value={term} autoComplete="off"
                aria-invalid={!!errors[`search-term-${index}`]}
                aria-describedby={["search-term-help", description(`search-term-${index}`)].filter(Boolean).join(' ')}
                onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }}
                onChange={event => update({ terms: draft.terms.map((value, i) => i === index ? event.target.value : value) })} />
              {draft.terms.length > 1 && <button type="button" onClick={() => update({ terms: draft.terms.filter((_, i) => i !== index) })}>Remove term {index + 1}</button>}
              {errors[`search-term-${index}`] && <p id={`search-term-${index}-error`} className="warning">{errors[`search-term-${index}`]}</p>}
            </div>)}
            <button type="button" disabled={draft.terms.length >= 16} onClick={() => update({ terms: [...draft.terms, ''] })}>Add term</button>
          </fieldset>
          <fieldset disabled={pending}>
            <legend>Kinds (none selected means all)</legend>
            <div className="search-kinds">{[...historyKinds, 'evidence'].map(kind => <label key={kind}>
              <input type="checkbox" checked={draft.kinds.includes(kind)} onChange={event => update({ kinds: event.target.checked ? [...draft.kinds, kind] : draft.kinds.filter(value => value !== kind) })} /> {kind}
            </label>)}</div>
          </fieldset>
          <div className="filter-bar">
            {(['since', 'until'] as const).map(field => <label key={field} htmlFor={`search-${field}`}>
              {field === 'since' ? 'Since' : 'Until'} (UTC)
              <input id={`search-${field}`} value={draft[field]} disabled={pending} placeholder="2026-10-10T00:00:00Z"
                aria-invalid={!!errors[`search-${field}`]} aria-describedby={description(`search-${field}`)} onChange={event => update({ [field]: event.target.value })} />
              {errors[`search-${field}`] && <span id={`search-${field}-error`} className="warning">{errors[`search-${field}`]}</span>}
            </label>)}
            <div><label htmlFor="search-limit">Result limit</label><select id="search-limit" value={draft.limit} disabled={pending} onChange={event => update({ limit: Number(event.target.value) })}>{[10, 25, 50].map(limit => <option key={limit}>{limit}</option>)}</select></div>
          </div>
          <div className="inspection-actions">
            <button className="search-submit" type="submit" disabled={pending || !permitted}>{pending ? 'Searching…' : 'Search'}</button>
            <button type="button" onClick={clear}>Clear search</button>
          </div>
        </form>
        {pending && <p role="status">Searching submitted terms…</p>}
        {error && <div className="error" role="alert"><p>{error}</p>{data && <p>Last valid result retained; this search refresh failed.</p>}<button disabled={pending} onClick={() => { if (state.submitted) void session.submit(state.submitted); }}>Retry submitted search</button></div>}
        {!state.submitted && !pending && <p className="empty">Enter one or more literal terms, then select Search.</p>}
        {data && <section className="panel search-results" aria-label="Submitted search results">
          <h2>Submitted search results</h2>
          <p>Showing submitted terms: {state.submitted?.terms.map((term, index) => <code key={index}>{term}{index + 1 < state.submitted!.terms.length ? ' · ' : ''}</code>)}. Editing the form does not change these results.</p>
          <p className="preview-note">{data.label}<br />{data.trust_label}</p>
          <div role="status"><strong>{data.coverage.complete ? 'Complete search coverage' : 'Incomplete search coverage'}</strong><p>Indexed through {data.coverage.indexed_through ?? 'Not supplied'}; historical entries {data.coverage.history_entries}.</p></div>
          <Reasons values={data.coverage.reasons} />
          {data.unverified && <p className="warning">Unverified references: {data.unverified.count}. No claim about these references is supplied.</p>}
          {!data.hits.length && <p>No matching verified references in this result.{!data.coverage.complete && ' Coverage is incomplete; this does not establish that no matching history exists.'}</p>}
          <div className="search-hits">{data.hits.map((hit, index) => <article className="panel search-hit" key={`${hit.kind}:${hit.id}:${index}`} data-search-hit={`${hit.kind}:${hit.id}:${index}`} onClickCapture={event => { if ((event.target as HTMLElement).closest('a')) rememberReference(`${hit.kind}:${hit.id}:${index}`); }}>
            <h3><code>{hit.id}</code> · <SemanticValue value={hit.kind} known={[...historyKinds, 'evidence']} /></h3>
            <p>Recorded UTC <time>{hit.at}</time> · Subject <code>{hit.subject ?? 'Not supplied'}</code></p>
            <p>{data.label}<br />{hit.trust.label} · <SemanticValue value={hit.trust.source} known={trustSources} /></p>
            <p>Source <SemanticValue value={hit.source} known={['history', 'evidence']} /></p>
            <div className="search-snippet" aria-label={`Plain-text historical snippet for ${hit.id}`}><code>{data.fence.open}</code><pre>{hit.snippet}</pre><code>{data.fence.close}</code></div>
            {hit.truncated && <p>Supplied snippet is truncated.</p>}
            {hit.expand.link && ['history', 'evidence'].includes(hit.expand.link.kind) ? <EntityAnchor entity={hit.expand.link} copyCli={false} /> : <p>No supported product expansion link supplied.</p>}
            {readOnlyHistoryArgv(hit.expand.cli) ? <CopyCli kind="history" id={hit.id} argv={hit.expand.cli} /> : <p>No supported read-only CLI expansion supplied.</p>}
          </article>)}</div>
          <details><summary>Source and browser metadata</summary><SourceStrip source={result!} failed={!!error || capabilities.isError} /></details>
        </section>}
      </CapabilityGate>}
  </section>;
}
