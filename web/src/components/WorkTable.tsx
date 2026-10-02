import { useState, useRef, useEffect } from 'react';
import { SemanticValue } from './States';
import { EntityAnchor } from './EntityAnchor';
import { ticketStates, parentStates } from '../api/vocabulary';
import { workTree, type Work } from '../pages/work-model';
export function WorkTable({
  items,
  tree,
}: {
  items: Work[];
  tree: boolean;
}) {
  const [collapsed, setCollapsed] = useState(new Set<string>());
  const [accessible, setAccessible] = useState(false);
  const [scroll, setScroll] = useState(0);
  const [height, setHeight] = useState(432);
  const viewport = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = viewport.current!;
    const update = () => setHeight(el.clientHeight || 432);
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (viewport.current) viewport.current.scrollTop = 0;
    setScroll(0);
  }, [tree]);
  const rows = tree
    ? workTree(items, collapsed)
    : items.map((item) => ({ item, depth: 0, expandable: false }));
  const start = accessible
    ? 0
    : Math.min(
        Math.max(0, rows.length - Math.ceil(height / 36)),
        Math.max(0, Math.floor(Math.max(0, scroll - 36) / 36) - 4),
      );
  const end = accessible
    ? rows.length
    : Math.min(rows.length, start + Math.ceil(height / 36) + 8);
  function spacer(pixels: number) {
    return (
      <tr className="virtual-spacer" aria-hidden="true">
        <td
          colSpan={5}
          ref={(el) => {
            if (el) el.style.height = `${pixels}px`;
          }}
        />
      </tr>
    );
  }
  return (
    <>
      <label className="accessibility-toggle">
        <input
          type="checkbox"
          checked={accessible}
          onChange={(e) => setAccessible(e.target.checked)}
        />{' '}
        Show every row on this page for keyboard navigation
      </label>
      <div
        ref={viewport}
        className={
          accessible ? 'table-scroll' : 'table-scroll virtual-scroll'
        }
        tabIndex={0}
        aria-label="Work rows"
        onScroll={(e) => setScroll(e.currentTarget.scrollTop)}
        onKeyDown={(e) => {
          if (e.target !== e.currentTarget) return;
          const steps: Record<string, number> = {
            ArrowDown: 36,
            ArrowUp: -36,
            PageDown: height,
            PageUp: -height,
          };
          if (e.key in steps) {
            e.preventDefault();
            e.currentTarget.scrollTop += steps[e.key];
          }
          if (e.key === 'Home' || e.key === 'End') {
            e.preventDefault();
            e.currentTarget.scrollTop =
              e.key === 'Home' ? 0 : e.currentTarget.scrollHeight;
          }
        }}
      >
        <table className="work-table" aria-rowcount={rows.length + 1}>
          <thead>
            <tr>
              <th>Work</th>
              <th>Kind</th>
              <th>State</th>
              <th>Record</th>
              <th>Parent</th>
            </tr>
          </thead>
          <tbody>
            {start > 0 && spacer(start * 36)}
            {rows
              .slice(start, end)
              .map(({ item: w, depth, expandable }, index) => (
                <tr key={w.id} aria-rowindex={start + index + 2}>
                  <td>
                    <div
                      className={`tree-cell depth-${Math.min(depth, 3)}`}
                    >
                      {expandable && (
                        <button
                          className="tree-toggle"
                          aria-label={`${collapsed.has(w.id) ? 'Expand' : 'Collapse'} ${w.title}`}
                          aria-expanded={!collapsed.has(w.id)}
                          onClick={() =>
                            setCollapsed((old) => {
                              const next = new Set(old);
                              if (next.has(w.id)) next.delete(w.id);
                              else next.add(w.id);
                              return next;
                            })
                          }
                        >
                          {collapsed.has(w.id) ? '+' : '−'}
                        </button>
                      )}
                      <EntityAnchor
                        entity={{ id: w.id, kind: 'work', title: w.title }}
                      />
                    </div>
                  </td>
                  <td>
                    <SemanticValue
                      value={w.kind}
                      known={['epic', 'story', 'ticket']}
                    />
                  </td>
                  <td>
                    <SemanticValue
                      value={w.state}
                      known={
                        w.kind === 'ticket' ? ticketStates : parentStates
                      }
                    />
                  </td>
                  <td>{w.archived ? 'Archived' : 'Hot'}</td>
                  <td>
                    {w.parent_id ? (
                      <EntityAnchor
                        entity={{ id: w.parent_id, kind: 'work' }}
                      />
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))}
            {end < rows.length && spacer((rows.length - end) * 36)}
          </tbody>
        </table>
        {!rows.length && (
          <p className="empty">No work matches these filters.</p>
        )}
      </div>
    </>
  );
}
