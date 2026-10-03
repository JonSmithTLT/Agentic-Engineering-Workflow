import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useSearchParams } from 'react-router-dom';
import { CopyDashboardLink } from './CopyDashboardLink';
const WorkspaceContext = createContext<string | null>(null);
export function useWorkspaceCollection() {
  return useContext(WorkspaceContext);
}
export function InvestigationWorkspace({
  collection,
  results,
  detail,
  title,
  resultsLabel = 'Results',
  selectionChanged,
}: {
  collection: 'work' | 'runs' | 'journal';
  title?: string;
  resultsLabel?: string;
  selectionChanged?: () => void;
  results: ReactNode;
  detail: (id: string, visible: boolean) => ReactNode;
}) {
  const [params, setParams] = useSearchParams(),
    selected = params.get('selected') ?? '';
  const [narrow, setNarrow] = useState(
      () => window.matchMedia?.('(max-width: 1023px)').matches ?? false,
    ),
    [pane, setPane] = useState('results');
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const media = window.matchMedia?.('(max-width: 1023px)');
    if (!media) return;
    const update = () => setNarrow(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    if (selected) setPane('detail');
  }, [selected]);
  return (
    <WorkspaceContext.Provider value={collection}>
      <h1 className="investigation-heading" tabIndex={-1} ref={heading}>
        {title ?? (collection === 'work' ? 'Work' : 'Runs') + ' investigation'}
      </h1>
      <div className="workspace-controls">
        <p>Inspect a record without losing your results.</p>
        {selected && <p className="workspace-selection" role={collection === 'journal' ? 'status' : undefined}>Selected: <code>{selected}</code></p>}
        <CopyDashboardLink />
        {selected && (
          <button
            onClick={() => {
              setParams((old) => {
                const p = new URLSearchParams(old);
                for (const k of ['selected', 'inspector', 'field', ...(collection === 'journal' ? ['panel'] : [])]) p.delete(k);
                return p;
              });
              setPane('results');
              heading.current?.focus();
              selectionChanged?.();
            }}
          >
            Close detail
          </button>
        )}
      </div>
      {narrow && selected && (
        <div
          className="workspace-switch"
          role="group"
          aria-label="Workspace pane"
        >
          <button
            aria-pressed={pane === 'results'}
            onClick={() => setPane('results')}
          >
            {resultsLabel}
          </button>
          <button
            aria-pressed={pane === 'detail'}
            onClick={() => setPane('detail')}
          >
            Detail <span aria-hidden="true">· {selected}</span>
          </button>
        </div>
      )}
      <div
        className={
          selected ? 'investigation-panes has-selection' : 'investigation-panes'
        }
      >
        <section
          className="investigation-results"
          hidden={narrow && selected !== '' && pane === 'detail'}
          aria-label="Investigation results"
        >
          {results}
        </section>
        {selected && (
          <section
            className="investigation-detail"
            hidden={narrow && pane === 'results'}
            aria-label="Selected record detail"
          >
            {detail(selected, !narrow || pane === 'detail')}
          </section>
        )}
      </div>
    </WorkspaceContext.Provider>
  );
}
