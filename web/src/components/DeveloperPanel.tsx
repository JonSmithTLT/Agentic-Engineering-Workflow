import { useEffect, useRef, useSyncExternalStore } from 'react';
import { requestLog } from '../api/diagnostics';
export function DeveloperPanel({ close }: { close: () => void }) {
  const traces = useSyncExternalStore(
    requestLog.subscribe,
    requestLog.snapshot,
  );
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
      <div className="panel-heading">
        <div>
          <h2>API requests</h2>
          <p>
            Last 200 completed requests · memory only · timings and diagnostics
            are browser observations
          </p>
        </div>
        <button onClick={requestLog.clear}>Clear log</button>
        <button onClick={close}>Close API panel</button>
      </div>
      <p className="scope-note">
        No cookies, authorization headers or response bodies are recorded. A 304
        shows the cached representation revision; it cannot prove the server’s
        live revision. Opening this panel sends no extra requests.
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
              {t.diagnostic && <p className="preview-note">{t.diagnostic}</p>}
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
    </section>
  );
}
