import { SemanticValue } from './States';
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import {
  investigate,
  knownExplanationValues,
  inspectionFieldValid,
  type EntityKind,
  type Investigation,
  type Source,
} from '../client/investigation-model';
import { historicalRequested } from '../api/navigation';
import { useReadSession } from '../client/queries';
import { id as identity } from '../api/schema';
import { Reasons } from './ProjectionViews';
import { RelationsExplorer } from './RelationsExplorer';
import { JsonContent } from './Content';
import { CopyDashboardLink } from './CopyDashboardLink';
type Controls = {
  target: Investigation | null;
  open: (target: Investigation, field?: string, relations?: boolean) => void;
  update: (target: Investigation, restore?: boolean) => void;
  retire: (key: string) => void;
};
const InspectorContext = createContext<Controls | null>(null);
export function SourceStrip({
  source,
  failed = false,
  readSnapshot,
}: {
  source: Source;
  failed?: boolean;
  readSnapshot?: string;
}) {
  const session = useReadSession();
  return (
    <div className="source-strip">
      <section aria-label="Source provenance">
        <h3>Source</h3>
        <dl>
          <dt>Project</dt>
          <dd>
            <code>{source.value.project_id}</code>
          </dd>
          <dt>Revision</dt>
          <dd>
            <code>{source.value.control_revision}</code>
          </dd>
          <dt>Generated</dt>
          <dd>
            <time>{source.value.generated_at}</time>
          </dd>
          <dt>Contract</dt>
          <dd>{source.value.schema_version}</dd>
        </dl>
      </section>
      <section aria-label="Browser observations">
        <h3>Browser</h3>
        <dl>
          <dt>Last checked</dt>
          <dd>
            <time>{source.last_checked_at}</time>
          </dd>
          <dt>Refresh state</dt>
          <dd>
            {failed ? 'STALE / DISCONNECTED' : 'CURRENT'} (this projection)
          </dd>
          <dt>Dataset</dt>
          <dd>
            {import.meta.env.MODE === 'demo' ? 'Demo data' : 'Live reads'}
          </dd>
          <dt>Snapshot</dt>
          <dd>{readSnapshot ?? session.identity.snapshot}</dd>
        </dl>
        <p className="muted">
          Browser observations; not backend health or provenance.
        </p>
      </section>
    </div>
  );
}
export function PresentationGuard({ children }: { children: ReactNode }) {
  const [params] = useSearchParams();
  const error = historicalRequested(params)
    ? 'Historical snapshot reads are not supported by this contract.'
    : params.has('selected') &&
        !identity.safeParse(params.get('selected')).success
      ? 'Locally malformed identifier. No projection request was sent.'
      : (params.has('inspector') &&
            !['why', 'relations'].includes(params.get('inspector')!)) ||
          !inspectionFieldValid(params.get('field'))
        ? 'Unsupported presentation value. No projection request was sent.'
        : '';
  return error ? (
    <p role="alert" className="preview-note">
      {error}
    </p>
  ) : (
    children
  );
}
export function InspectorProvider({ children }: { children: ReactNode }) {
  const [params, setParams] = useSearchParams(),
    location = useLocation();
  const [target, setTarget] = useState<Investigation | null>(null);
  const [wide, setWide] = useState(
    () => window.matchMedia?.('(min-width: 1440px)').matches ?? true,
  );
  const dialog = useRef<HTMLDialogElement>(null),
    heading = useRef<HTMLHeadingElement>(null),
    trigger = useRef<HTMLElement | null>(null);
  const panel = params.get('inspector'),
    field = params.get('field');
  const active = !!target && ['why', 'relations'].includes(panel ?? '');
  useEffect(() => {
    const media = window.matchMedia?.('(min-width: 1440px)');
    if (!media) return;
    const update = () => setWide(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  function close() {
    setParams((old) => {
      const next = new URLSearchParams(old);
      next.delete('inspector');
      next.delete('field');
      return next;
    });
    const fallback = document.querySelector<HTMLElement>(
      '.investigation-heading, #content',
    );
    (trigger.current?.isConnected ? trigger.current : fallback)?.focus();
  }
  useEffect(() => {
    if (!active) return;
    if (!wide) dialog.current?.showModal();
    heading.current?.focus();
    return () => {
      if (dialog.current?.open) dialog.current.close();
    };
  }, [active, wide]);
  const update = (next: Investigation, restore = false) =>
    setTarget((old) => (restore || old?.key === next.key ? next : old));
  const controls: Controls = {
    target,
    update,
    retire: (key) => setTarget((old) => (old?.key === key ? null : old)),
    open: (next, f, relations = false) => {
      trigger.current = document.activeElement as HTMLElement;
      setTarget(next);
      setParams((old) => {
        const p = new URLSearchParams(old);
        p.set('inspector', relations ? 'relations' : 'why');
        if (f) p.set('field', f);
        else p.delete('field');
        if (
          !/\/(work|runs|evidence|knowledge|history)\/[^/]+$/.test(
            location.pathname,
          )
        )
          p.set('selected', next.id);
        return p;
      });
    },
  };
  const explanation =
    target?.explanations.find((e) => e.field === field) ??
    (field ? undefined : target?.explanations[0]);
  const content = target ? (
    <>
      <div className="inspector-heading">
        <h2 tabIndex={-1} ref={heading}>
          Inspect {target.id}
        </h2>
        <button onClick={close} aria-label="Close inspector">
          Close
        </button>
      </div>
      <div
        role="tablist"
        aria-label="Investigation inspector"
        onKeyDown={(e) => {
          if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) {
            e.preventDefault();
            const next = panel === 'why' ? 'relations' : 'why';
            setParams((old) => {
              const p = new URLSearchParams(old);
              p.set('inspector', next);
              return p;
            });
            e.currentTarget
              .querySelector<HTMLButtonElement>(`[data-tab="${next}"]`)
              ?.focus();
          }
        }}
      >
        {['why', 'relations'].map((tab) => (
          <button
            key={tab}
            data-tab={tab}
            role="tab"
            aria-selected={panel === tab}
            tabIndex={panel === tab ? 0 : -1}
            onClick={() =>
              setParams((old) => {
                const p = new URLSearchParams(old);
                p.set('inspector', tab);
                return p;
              })
            }
          >
            {tab === 'why' ? 'Why' : 'Relations'}
          </button>
        ))}
      </div>
      <SourceStrip source={target.source} failed={target.failed} />
      <div role="tabpanel" aria-label="Why" hidden={panel !== 'why'}>
        {explanation ? (
          <>
            <h3>
              <code>{explanation.field}</code>: {explanation.value}
            </h3>
            <p>
              {explanation.bound
                ? 'Reasons supplied for this field.'
                : 'Reasons supplied for this record; no explicit binding to this status.'}
            </p>
            {explanation.value !== 'Not supplied' &&
              !knownExplanationValues(
                target.kind,
                explanation.field,
                target.record,
              ).includes(explanation.value) && (
                <SemanticValue value={explanation.value} known={[]} />
              )}
            <Reasons values={explanation.reasons} />
            {!explanation.reasons.length && (
              <p>No explanation supplied for this status.</p>
            )}
            {explanation.sections.map((s) => (
              <section key={s.name}>
                <h4>Supplied {s.name}</h4>
                <Reasons values={s.reasons} />
              </section>
            ))}
            <p className="muted">
              Reason codes are opaque. Associated references do not establish an
              explanation.
            </p>
          </>
        ) : (
          <p>No explanation supplied.</p>
        )}
      </div>
      <div
        role="tabpanel"
        aria-label="Relations"
        hidden={panel !== 'relations'}
      >
        <RelationsExplorer key={target.key} root={target} />
      </div>
      {target.kind === 'history' && (
        <section>
          <h3>Supplied manifest identity</h3>
          <JsonContent
            value={{
              seq: (target.record as { seq: number }).seq,
              sha256: (target.record as { sha256: string }).sha256,
            }}
          />
        </section>
      )}
      {target.kind === 'integrity' && (
        <section>
          <h3>Supplied integrity roots</h3>
          <JsonContent
            value={{
              current_root: (target.record as { current_root: unknown })
                .current_root,
              verified: (target.record as { verified: unknown }).verified,
              last_full: (target.record as { last_full: unknown }).last_full,
            }}
          />
        </section>
      )}
      <CopyDashboardLink />
    </>
  ) : null;
  return (
    <InspectorContext.Provider value={controls}>
      <div
        className={
          active && wide
            ? 'investigation-layout inspector-open'
            : 'investigation-layout'
        }
      >
        <div className="investigation-content">{children}</div>
        {wide && target && (
          <aside
            className="inspector-panel"
            hidden={!active}
            aria-label="Investigation inspector"
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                e.stopPropagation();
                close();
              }
            }}
          >
            {content}
          </aside>
        )}
      </div>
      {!wide && target && (
        <dialog
          className="inspector-dialog"
          ref={dialog}
          aria-label="Investigation inspector"
          onCancel={(e) => {
            e.preventDefault();
            close();
          }}
        >
          {content}
        </dialog>
      )}
    </InspectorContext.Provider>
  );
}
export function RecordInspection({
  kind,
  record,
  source,
  fallbackId,
  failed = false,
}: {
  kind: EntityKind;
  record: unknown;
  source: Source;
  fallbackId?: string;
  failed?: boolean;
}) {
  const controls = useContext(InspectorContext),
    [params] = useSearchParams();
  const target = { ...investigate(kind, record, source, fallbackId), failed };
  const signature = JSON.stringify(target);
  useEffect(() => {
    if (!controls) return;
    controls.update(
      target,
      params.has('inspector') &&
        (!params.has('selected') || params.get('selected') === target.id),
    );
    // Validated data updates the selected source without replacing navigation state.
  }, [signature, params.get('inspector'), params.get('selected')]);
  useEffect(
    () => () => {
      controls?.retire(target.key);
    },
    [target.key],
  );
  return (
    <section className="record-inspection" aria-label={`Inspect ${target.id}`}>
      <div className="inspection-actions">
        {controls &&
          target.explanations.map((e) => (
            <button
              key={e.field}
              onClick={() => controls.open(target, e.field)}
            >
              Why {e.field}: {e.value}
            </button>
          ))}
        {controls && (
          <button onClick={() => controls.open(target, undefined, true)}>
            Inspect relations
          </button>
        )}
        <CopyDashboardLink />
      </div>
      <SourceStrip source={source} failed={failed} />
    </section>
  );
}
