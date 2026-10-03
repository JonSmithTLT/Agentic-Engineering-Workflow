import { useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { Work } from '../pages/work-model';
import { graphCard, workGraph } from '../pages/work-graph-model';
import { EntityAnchor } from './EntityAnchor';
import { SemanticValue } from './States';
import { Reasons, References } from './ProjectionViews';
import { SafeContent } from './Content';
import { parentStates, ticketStates } from '../api/vocabulary';
export function WorkGraph({ items }: { items: Work[] }) {
  const [params, setParams] = useSearchParams();
  const focus = params.get('focus') ?? '';
  const [collapsed, setCollapsed] = useState(new Set<string>());
  const [selection, setSelection] = useState('');
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const viewport = useRef<HTMLDivElement>(null);
  const drag = useRef<{
    x: number;
    y: number;
    left: number;
    top: number;
    panX: number;
    panY: number;
    fitsX: boolean;
    fitsY: boolean;
  } | null>(null);
  const graph = workGraph(items, collapsed, focus);
  const selected = graph.choices.find((node) => node.id === selection);
  const selectedVisible = graph.nodes.some((node) => node.id === selection);
  const current = selected?.item;
  function center(id: string) {
    const node = graph.nodes.find((node) => node.id === id);
    if (node && viewport.current) {
      setPan({ x: 0, y: 0 });
      viewport.current.scrollLeft =
        (node.x + graphCard.width / 2) * zoom -
        viewport.current.clientWidth / 2;
      viewport.current.scrollTop =
        (node.y + graphCard.height / 2) * zoom -
        viewport.current.clientHeight / 2;
    }
  }
  return (
    <div className="work-graph">
      <div className="graph-toolbar">
        <label>
          Focus on
          <select
            aria-label="Graph focus"
            value={focus}
            onChange={(e) => {
              setParams((old) => {
                const next = new URLSearchParams(old);
                if (e.target.value) next.set('focus', e.target.value);
                else next.delete('focus');
                return next;
              });
              setPan({ x: 0, y: 0 });
              if (viewport.current) {
                viewport.current.scrollTop = 0;
                viewport.current.scrollLeft = 0;
              }
            }}
          >
            <option value="">All records on this page</option>
            {focus && graph.focusMissing && (
              <option value={focus}>{focus} — outside this page</option>
            )}
            {graph.choices.map((node) => (
              <option key={node.id} value={node.id}>
                {node.id} ·{' '}
                {node.item?.title ?? 'Parent reference outside this page'}
              </option>
            ))}
          </select>
        </label>
        <div className="graph-zoom" role="group" aria-label="Graph zoom">
          <button
            aria-label="Zoom out"
            disabled={zoom <= 0.4}
            onClick={() => setZoom((old) => Math.max(0.4, old - 0.15))}
          >
            −
          </button>
          <output aria-label="Zoom level">{Math.round(zoom * 100)}%</output>
          <button
            aria-label="Zoom in"
            disabled={zoom >= 1.6}
            onClick={() => setZoom((old) => Math.min(1.6, old + 0.15))}
          >
            +
          </button>
          <button
            onClick={() => {
              setZoom(1);
              setPan({ x: 0, y: 0 });
            }}
          >
            Reset zoom
          </button>
          <button
            onClick={() => {
              setPan({ x: 0, y: 0 });
              setZoom(
                Math.min(
                  1,
                  Math.max(
                    0.4,
                    (viewport.current?.clientWidth ?? 700) / graph.width,
                  ),
                ),
              );
              if (viewport.current) {
                viewport.current.scrollLeft = 0;
                viewport.current.scrollTop = 0;
              }
            }}
          >
            Fit width
          </button>
        </div>
        <button
          disabled={!collapsed.size}
          onClick={() => setCollapsed(new Set())}
        >
          Expand all
        </button>
      </div>
      <p className="graph-scope" role="note">
        Loaded page only. Arrows show parent → child; dashed cards are parent
        IDs whose records are outside this page. Drag empty space to pan, or
        focus the canvas and use arrow keys. Use Table or Tree for linear
        inspection.
      </p>
      <div className="graph-layout">
        <div
          className="graph-viewport"
          ref={viewport}
          tabIndex={0}
          aria-label="Work graph canvas"
          onPointerDown={(e) => {
            if (
              e.button !== 0 ||
              (e.target as Element).closest('button, a, select, input')
            )
              return;
            drag.current = {
              x: e.clientX,
              y: e.clientY,
              left: e.currentTarget.scrollLeft,
              top: e.currentTarget.scrollTop,
              panX: pan.x,
              panY: pan.y,
              fitsX: graph.width * zoom <= e.currentTarget.clientWidth,
              fitsY: graph.height * zoom <= e.currentTarget.clientHeight,
            };
            e.currentTarget.setPointerCapture(e.pointerId);
            e.currentTarget.classList.add('panning');
          }}
          onPointerMove={(e) => {
            if (drag.current) {
              const motion = drag.current;
              const dx = e.clientX - motion.x,
                dy = e.clientY - motion.y;
              if (!drag.current.fitsX)
                e.currentTarget.scrollLeft = drag.current.left - dx;
              if (!drag.current.fitsY)
                e.currentTarget.scrollTop = drag.current.top - dy;
              setPan((old) => ({
                x: motion.fitsX ? motion.panX + dx : old.x,
                y: motion.fitsY ? motion.panY + dy : old.y,
              }));
            }
          }}
          onPointerUp={(e) => {
            drag.current = null;
            e.currentTarget.classList.remove('panning');
            if (e.currentTarget.hasPointerCapture(e.pointerId))
              e.currentTarget.releasePointerCapture(e.pointerId);
          }}
          onPointerCancel={(e) => {
            drag.current = null;
            e.currentTarget.classList.remove('panning');
          }}
          onKeyDown={(e) => {
            if (e.target !== e.currentTarget) return;
            const steps: Record<string, [number, number]> = {
              ArrowRight: [100, 0],
              ArrowLeft: [-100, 0],
              ArrowDown: [0, 100],
              ArrowUp: [0, -100],
            };
            if (e.key in steps) {
              e.preventDefault();
              const [dx, dy] = steps[e.key];
              const fitsX = graph.width * zoom <= e.currentTarget.clientWidth;
              const fitsY = graph.height * zoom <= e.currentTarget.clientHeight;
              if (!fitsX) e.currentTarget.scrollLeft += dx;
              if (!fitsY) e.currentTarget.scrollTop += dy;
              setPan((old) => ({
                x: fitsX ? old.x - dx : old.x,
                y: fitsY ? old.y - dy : old.y,
              }));
            }
          }}
        >
          {graph.focusMissing ? (
            <p className="empty">
              This focus ID is not on the loaded page. Choose another focus or
              inspect the record through Work.
            </p>
          ) : !graph.nodes.length ? (
            <p className="empty">No work matches these filters.</p>
          ) : (
            <div
              className="graph-extent"
              ref={(el) => {
                if (el) {
                  el.style.width = `${graph.width * zoom}px`;
                  el.style.height = `${graph.height * zoom}px`;
                }
              }}
            >
              <div
                className="graph-surface"
                ref={(el) => {
                  if (el) {
                    el.style.width = `${graph.width}px`;
                    el.style.height = `${graph.height}px`;
                    el.style.transform = `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`;
                  }
                }}
              >
                <svg
                  className="graph-edges"
                  width={graph.width}
                  height={graph.height}
                  aria-hidden="true"
                >
                  <defs>
                    <marker
                      id="work-parent-arrow"
                      viewBox="0 0 8 8"
                      refX="7"
                      refY="4"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 0 L 8 4 L 0 8 z" />
                    </marker>
                  </defs>
                  {graph.edges.map((edge) => {
                    const x1 = edge.parent.x + graphCard.width,
                      y1 = edge.parent.y + graphCard.height / 2,
                      x2 = edge.child.x,
                      y2 = edge.child.y + graphCard.height / 2,
                      bend = Math.max(22, Math.abs(x2 - x1) / 2);
                    return (
                      <path
                        key={`${edge.parent.id}:${edge.child.id}`}
                        className={
                          edge.parent.id === selection ||
                          edge.child.id === selection
                            ? 'selected-edge'
                            : ''
                        }
                        d={`M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`}
                        markerEnd="url(#work-parent-arrow)"
                      />
                    );
                  })}
                </svg>
                {graph.nodes.map((node) => (
                  <div
                    key={node.id}
                    className={`graph-card${node.item ? '' : ' reference-card'}${node.id === selection ? ' selected-card' : ''}`}
                    ref={(el) => {
                      if (el) {
                        el.style.left = `${node.x}px`;
                        el.style.top = `${node.y}px`;
                      }
                    }}
                  >
                    <button
                      className="graph-select"
                      aria-label={`Select ${node.id}${node.item ? ': ' + node.item.title : ': parent outside this page'}`}
                      aria-pressed={node.id === selection}
                      onClick={() => setSelection(node.id)}
                    >
                      <code>{node.id}</code>
                      <span className="graph-title">
                        {node.item?.title ?? 'Parent outside this page'}
                      </span>
                      <span className="graph-node-meta">
                        {node.item ? (
                          <>
                            <SemanticValue
                              value={node.item.kind}
                              known={['epic', 'story', 'ticket']}
                            />
                            <SemanticValue
                              value={node.item.state}
                              known={
                                node.item.kind === 'ticket'
                                  ? ticketStates
                                  : parentStates
                              }
                            />
                          </>
                        ) : (
                          <span className="muted">Reference only</span>
                        )}
                      </span>
                      {node.item?.archived && (
                        <span className="graph-historical">
                          Historical record
                        </span>
                      )}
                    </button>
                    {!!node.children.length && (
                      <button
                        className="graph-collapse"
                        aria-label={`${collapsed.has(node.id) ? 'Expand' : 'Collapse'} branch ${node.id}`}
                        aria-expanded={!collapsed.has(node.id)}
                        onClick={() =>
                          setCollapsed((old) => {
                            const next = new Set(old);
                            if (next.has(node.id)) next.delete(node.id);
                            else next.add(node.id);
                            return next;
                          })
                        }
                      >
                        {collapsed.has(node.id) ? '+' : '−'}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <aside className="graph-inspector" aria-label="Selected graph record">
          {!selected ? (
            <>
              <h3>Inspect a record</h3>
              <p>
                Select a card to see its context and links. The graph rearranges
                the backend parent relationships on this page.
              </p>
            </>
          ) : (
            <>
              <h3>{selected.item?.title ?? 'Parent reference'}</h3>
              <code>{selected.id}</code>
              <p>
                <EntityAnchor
                  entity={{
                    id: selected.id,
                    kind: 'work',
                    title: 'Open Work detail',
                  }}
                />
              </p>
              {selectedVisible ? (
                <button onClick={() => center(selected.id)}>
                  Center selected record
                </button>
              ) : (
                <p className="muted">
                  The selection is hidden by this focus or a collapsed branch.
                </p>
              )}
              {current ? (
                <>
                  <p>
                    {current.archived
                      ? 'Historical reference; never current evidence.'
                      : 'Record is in the loaded Work projection.'}
                  </p>
                  <SafeContent {...current.summary} />
                  <dl>
                    <dt>Risk class</dt>
                    <dd>{current.risk_class ?? 'Not supplied'}</dd>
                    <dt>Parent</dt>
                    <dd>
                      {current.parent_id ? (
                        <EntityAnchor
                          entity={{ id: current.parent_id, kind: 'work' }}
                        />
                      ) : (
                        'None supplied'
                      )}
                    </dd>
                  </dl>
                  {current.rollup && (
                    <>
                      <h4>Backend subtree Ticket counts</h4>
                      <dl>
                        <dt>Open</dt>
                        <dd>{current.rollup.open}</dd>
                        <dt>Done</dt>
                        <dd>{current.rollup.done}</dd>
                        <dt>Cancelled</dt>
                        <dd>{current.rollup.cancelled}</dd>
                      </dl>
                    </>
                  )}
                  {current.children_truncated && (
                    <p className="preview-note">
                      The backend child preview is truncated. This graph is also
                      limited to the current page.
                    </p>
                  )}
                  <h4>Backend reasons</h4>
                  <Reasons
                    values={[...current.blocked_by, ...current.reasons]}
                  />
                  <h4>Related records</h4>
                  <References values={current.related} />
                </>
              ) : (
                <p>
                  This parent ID is supplied by a child record. Its own title,
                  state and ancestors are not included in this page.
                </p>
              )}
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
