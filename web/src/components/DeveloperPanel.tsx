import {
  useEffect,
  useRef,
  useSyncExternalStore,
  useState,
  type ComponentType,
} from 'react';
import { requestLog } from '../api/diagnostics';
export function DeveloperPanel({
  close,
  demoLab: DemoLab,
}: {
  close: () => void;
  demoLab?: ComponentType<{ tab: string }>;
}) {
  const traces = useSyncExternalStore(
    requestLog.subscribe,
    requestLog.snapshot,
  );
  const [tab, setTab] = useState('Requests');
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    panel.current?.focus();
  }, []);
  return (
    <section
      className="developer-panel"
      aria-label="API developer panel"
      tabIndex={-1}
      ref={panel}
      onKeyDown={(e) => {
        if (e.key === 'Escape') close();
      }}
    >
      <div className="developer-toolbar">
        <div className="panel-heading">
          <div>
            <h2>API requests</h2>
            <p>
              Last 200 completed requests · memory only · timings and
              diagnostics are browser observations
            </p>
          </div>
          <button onClick={requestLog.clear}>Clear log</button>
          <button onClick={close}>Close API panel</button>
        </div>
        {DemoLab && (
          <div
            role="tablist"
            aria-label="Developer tools tabs"
            className="lab-tabs"
          >
            {['Requests', 'Scenarios', 'Contract'].map((name, i) => (
              <button
                key={name}
                role="tab"
                aria-selected={tab === name}
                tabIndex={tab === name ? 0 : -1}
                onClick={() => setTab(name)}
                onKeyDown={(e) => {
                  if (
                    ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)
                  ) {
                    e.preventDefault();
                    const index =
                      e.key === 'Home'
                        ? 0
                        : e.key === 'End'
                          ? 2
                          : (i + (e.key === 'ArrowRight' ? 1 : 2)) % 3;
                    setTab(['Requests', 'Scenarios', 'Contract'][index]);
                    (
                      e.currentTarget.parentElement?.children[
                        index
                      ] as HTMLElement
                    )?.focus();
                  }
                }}
              >
                {name}
              </button>
            ))}
          </div>
        )}
      </div>
      {tab === 'Requests' ? (
        <div role="tabpanel" aria-label="Requests">
          <p className="scope-note">
            No cookies, authorization headers or response bodies are recorded. A
            304 shows the cached representation revision; it cannot prove the
            server’s live revision. Opening this panel sends no extra requests.
          </p>
          <div className="developer-requests">
            {!traces.length ? (
              <p>No requests recorded yet.</p>
            ) : (
              traces.map((t) => (
                <details
                  key={t.id}
                  className={t.error || t.diagnostic ? 'request-issue' : ''}
                >
                  <summary>
                    <code>{t.path}</code>
                    <span>{t.status ?? 'Network error'}</span>
                    <span>{t.duration_ms} ms</span>
                    <span>rev {t.control_revision ?? '—'}</span>
                    {t.error && <strong>{t.error}</strong>}
                    {t.diagnostic && <strong>ETag observation</strong>}
                  </summary>
                  <dl>
                    <dt>Read context</dt>
                    <dd>
                      <code>{t.context ?? 'Unspecified'}</code>
                    </dd>
                    <dt>Started</dt>
                    <dd>{t.started_at}</dd>
                    <dt>Project</dt>
                    <dd>{t.project_id ?? 'No validated representation'}</dd>
                    <dt>Sent If-None-Match</dt>
                    <dd>
                      <code>{t.request_etag ?? 'None'}</code>
                    </dd>
                    <dt>Response ETag</dt>
                    <dd>
                      <code>{t.response_etag ?? 'None'}</code>
                    </dd>
                    <dt>Representation ETag</dt>
                    <dd>
                      <code>{t.represented_etag ?? 'None'}</code>
                    </dd>
                  </dl>
                  {t.diagnostic && (
                    <p className="preview-note">{t.diagnostic}</p>
                  )}
                  {t.validation.length > 0 && (
                    <ul>
                      {t.validation.map((v, i) => (
                        <li key={i}>
                          <code>{v.field}</code> · {v.code} · {v.message}
                        </li>
                      ))}
                    </ul>
                  )}
                </details>
              ))
            )}
          </div>
        </div>
      ) : (
        DemoLab && <DemoLab key={tab} tab={tab} />
      )}
    </section>
  );
}
