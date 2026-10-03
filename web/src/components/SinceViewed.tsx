import { SemanticValue } from './States';
import { workStates, invocationStatuses } from '../api/vocabulary';
import { useEffect, useMemo, useState } from 'react';
import {
  clearViews,
  compareView,
  readView,
  rememberView,
  savedView,
} from '../client/view-memory';
export function SinceViewed({
  project,
  scope,
  revision,
  items,
}: {
  project: string;
  scope: string;
  revision: string;
  items: { id: string; state?: string | null }[];
}) {
  const [storageError, setStorageError] = useState(false),
    [paused, setPaused] = useState(false);
  const [baseline, setBaseline] = useState(() => {
    try {
      return readView(window.localStorage, project, scope);
    } catch {
      return undefined;
    }
  });
  const current = useMemo(
    () =>
      savedView.safeParse({
        project,
        scope,
        revision,
        at: new Date().toISOString(),
        items: items
          .slice(0, 100)
          .map((i) => ({ id: i.id, state: i.state ?? null })),
      }),
    [project, scope, revision, items],
  );
  useEffect(() => {
    function save() {
      if (paused || document.visibilityState !== 'visible' || !current.success)
        return;
      try {
        rememberView(window.localStorage, current.data);
      } catch {
        setStorageError(true);
      }
    }
    save();
    document.addEventListener('visibilitychange', save);
    return () => document.removeEventListener('visibilitychange', save);
  }, [current, paused]);
  const result =
    baseline && current.success
      ? compareView(baseline, current.data)
      : undefined;
  return (
    <details className="since-viewed">
      <summary>
        Since you last looked{' '}
        <span className="muted">· Browser comparison of this page</span>
      </summary>
      <p className="scope-note">
        Up to 100 loaded IDs and states per page, for 20 project/view scopes,
        are remembered locally. This is not an AEW event log or backend count.
        Missing rows can have left this page; they are not reported as deleted.
        Demo and live scopes are separate.
      </p>
      {storageError || !current.success ? (
        <p>
          Browser storage is unavailable or this page exceeds the snapshot
          bounds. The dashboard still works.
        </p>
      ) : paused ? (
        <p>
          Saved comparisons cleared; remembering is paused until you leave this
          page.
        </p>
      ) : !baseline ? (
        <p>
          No previous snapshot. This page is remembered for your next visit.
        </p>
      ) : result?.older ? (
        <p>
          Saved revision {baseline.revision} is newer than this projection.
          Comparison paused; saved snapshot preserved.
        </p>
      ) : (
        <>
          <p>
            Compared with revision {baseline.revision}, viewed {baseline.at}.
            Current revision {revision}.
          </p>
          {result?.changes.length ? (
            <ul>
              {result.changes.map((c) => (
                <li key={c.id}>
                  <code>{c.id}</code> ·{' '}
                  {c.from === undefined ? (
                    'New to this loaded page'
                  ) : (
                    <>
                      {c.from === null ? (
                        'No state'
                      ) : (
                        <SemanticValue
                          value={c.from}
                          known={
                            scope.startsWith('work:')
                              ? workStates
                              : invocationStatuses
                          }
                        />
                      )}{' '}
                      →{' '}
                      {c.to === null ? (
                        'No state'
                      ) : (
                        <SemanticValue
                          value={c.to}
                          known={
                            scope.startsWith('work:')
                              ? workStates
                              : invocationStatuses
                          }
                        />
                      )}
                    </>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p>No ID or state differences in the loaded page.</p>
          )}
        </>
      )}
      <button
        onClick={() => {
          try {
            clearViews(window.localStorage);
            setPaused(true);
            setBaseline(undefined);
          } catch {
            setStorageError(true);
          }
        }}
      >
        Clear saved comparisons
      </button>
    </details>
  );
}
