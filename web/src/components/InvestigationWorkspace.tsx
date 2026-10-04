import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useNavigationType, useSearchParams } from 'react-router-dom';
import { CopyDashboardLink } from './CopyDashboardLink';
import { focusBelowHeader } from './InvestigationTabs';
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
  const resultsRef = useRef<HTMLElement>(null);
  const detailRef = useRef<HTMLElement>(null);
  const resultLink = useRef<HTMLAnchorElement | null>(null);
  const navigationType = useNavigationType();
  const navigationRef = useRef(navigationType);
  useEffect(() => { navigationRef.current = navigationType; }, [navigationType]);
  const workPane = collection === 'work' ? params.get('work_pane') : null;
  const activePane =
    workPane === 'results' || workPane === 'detail' ? workPane : pane;
  function switchPane(value: 'results' | 'detail') {
    setPane(value);
    if (collection === 'work')
      setParams(old => {
        const next = new URLSearchParams(old);
        next.set('work_pane', value);
        return next;
      });
  }
  useEffect(() => {
    if (collection !== 'work') return;
    const showingResults = workPane === 'results';
    if (!showingResults && (!narrow || !selected || activePane !== 'detail')) return;
    const root = showingResults ? resultsRef.current : detailRef.current;
    if (!root) return;
    let cancelled = false;
    let frame = 0;
    let scheduled = false;
    function target() {
      if (showingResults) {
        const link = resultLink.current;
        return navigationRef.current === 'POP' && link?.isConnected && root!.contains(link)
          ? link : root!.querySelector<HTMLElement>('h1');
      }
      return [...root!.querySelectorAll<HTMLElement>('[data-work-heading]')]
        .find(element => element.dataset.workHeading === selected) ?? null;
    }
    const schedule = () => {
      if (scheduled || !target()) return;
      scheduled = true;
      // History restores document scroll after the route update. Wait for that
      // restoration before bringing the actual focus target below the header.
      frame = requestAnimationFrame(() => {
        frame = requestAnimationFrame(() => {
          if (!cancelled) focusBelowHeader(target());
          observer.disconnect();
        });
      });
    };
    const observer = new MutationObserver(schedule);
    observer.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-work-heading'] });
    schedule(); // Detail may already be cached; otherwise wait for its heading.
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [collection, workPane, selected, narrow, activePane]);
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
                for (const k of ['selected', 'inspector', 'field', ...(collection === 'work' ? ['work_pane'] : []), ...(collection === 'journal' ? ['panel'] : [])]) p.delete(k);
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
            aria-pressed={activePane === 'results'}
            onClick={() => switchPane('results')}
          >
            {resultsLabel}
          </button>
          <button
            aria-pressed={activePane === 'detail'}
            onClick={() => switchPane('detail')}
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
          ref={resultsRef}
          onClickCapture={event => {
            if (collection !== 'work') return;
            const link = (event.target as Element).closest<HTMLAnchorElement>('a[href]');
            if (link && new URL(link.href).searchParams.has('selected')) resultLink.current = link;
          }}
          className="investigation-results"
          hidden={narrow && selected !== '' && activePane === 'detail'}
          aria-label="Investigation results"
        >
          {results}
        </section>
        {selected && (
          <section
            ref={detailRef}
            className="investigation-detail"
            hidden={narrow && activePane === 'results'}
            aria-label="Selected record detail"
          >
            {detail(selected, !narrow || activePane === 'detail')}
          </section>
        )}
      </div>
    </WorkspaceContext.Provider>
  );
}
