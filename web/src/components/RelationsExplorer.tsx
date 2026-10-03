import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  investigate,
  type Investigation,
  type EntityKind,
  type Relation,
} from '../client/investigation-model';
import { transport } from '../api/transport';
import { responseSchemas } from '../api/schema';
import { projectionKey } from '../client/queries';
import { useDashboard } from '../client/dashboard';
import { capabilityView } from '../api/capabilities';
import { EntityAnchor } from './EntityAnchor';
import { SourceStrip } from './Investigation';
type Node = {
  key: string;
  kind: string;
  id: string;
  depth: number;
  loaded?: Investigation;
  expanded?: boolean;
  error?: string;
};
type Edge = {
  key: string;
  from: string;
  to: string;
  relation: Relation;
  source: Investigation;
};
const descriptors = {
  work: { path: 'work', schema: responseSchemas.WorkResponse },
  invocation: { path: 'runs', schema: responseSchemas.InvocationResponse },
  evidence: { path: 'evidence', schema: responseSchemas.EvidenceResponse },
  knowledge: { path: 'knowledge', schema: responseSchemas.KnowledgeResponse },
  history: { path: 'history', schema: responseSchemas.HistoryResponse },
};
const limits = { nodes: 24, edges: 80, depth: 3 };
export function RelationsExplorer({ root }: { root: Investigation }) {
  const initial: Node = {
    key: root.key,
    kind: root.kind,
    id: root.id,
    depth: 0,
    loaded: root,
  };
  const [nodes, setNodes] = useState<Node[]>([initial]),
    [edges, setEdges] = useState<Edge[]>([]),
    [busy, setBusy] = useState(''),
    [omitted, setOmitted] = useState(0),
    [mode, setMode] = useState('graph'),
    [page, setPage] = useState(0),
    [selected, setSelected] = useState<Edge | null>(null),
    [zoom, setZoom] = useState(1),
    [pan, setPan] = useState({ x: 0, y: 0 });
  const client = useQueryClient(),
    { caps } = useDashboard(),
    viewport = useRef<HTMLDivElement>(null),
    mounted = useRef(true),
    controller = useRef<AbortController | null>(null),
    drag = useRef<{ x: number; y: number; px: number; py: number } | null>(
      null,
    );
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controller.current?.abort();
    };
  }, []);
  const allRelations = nodes.flatMap(
    (n) =>
      n.loaded?.relations.map((r, index) => ({
        key: n.key + ':' + index,
        from: n.key,
        to: r.target.kind + ':' + r.target.id,
        relation: r,
        source: n.loaded!,
      })) ?? [],
  );
  function allowed(node: Node) {
    const d = Object.hasOwn(descriptors, node.kind)
      ? descriptors[node.kind as keyof typeof descriptors]
      : undefined;
    return d && capabilityView(caps?.[d.path]).available;
  }
  async function expand(node: Node) {
    if (
      busy ||
      node.expanded ||
      node.depth >= limits.depth ||
      (!node.loaded && !allowed(node))
    )
      return;
    setBusy(node.key);
    const abort = new AbortController();
    controller.current = abort;
    const context = transport.context;
    try {
      let loaded = node.loaded;
      if (!loaded) {
        const d = Object.hasOwn(descriptors, node.kind)
          ? descriptors[node.kind as keyof typeof descriptors]
          : undefined;
        if (!d) return;
        const route = `/${d.path}/${encodeURIComponent(node.id)}${node.kind === 'history' ? '?annotations_limit=100' : ''}`;
        const result = await client.fetchQuery({
          queryKey: projectionKey(route),
          queryFn: () =>
            transport.get(
              route,
              d.schema as typeof responseSchemas.WorkResponse,
              abort.signal,
            ),
        });
        loaded = investigate(
          node.kind as EntityKind,
          result.value.data,
          result,
        );
      }
      if (!mounted.current || context.retired || abort.signal.aborted) return;
      const additions: Node[] = [],
        connections: Edge[] = [],
        known = new Set(nodes.map((n) => n.key));
      let skipped = 0;
      loaded.relations.forEach((relation, index) => {
        const key = relation.target.kind + ':' + relation.target.id;
        if (edges.length + connections.length >= limits.edges) {
          skipped++;
          return;
        }
        if (!known.has(key)) {
          if (nodes.length + additions.length >= limits.nodes) {
            skipped++;
            return;
          }
          known.add(key);
          additions.push({
            key,
            kind: relation.target.kind,
            id: relation.target.id,
            depth: node.depth + 1,
          });
        }
        connections.push({
          key: node.key + ':' + index,
          from: node.key,
          to: key,
          relation,
          source: loaded!,
        });
      });
      setNodes((old) => [
        ...old.map((n) =>
          n.key === node.key
            ? { ...n, loaded, expanded: true, error: undefined }
            : n,
        ),
        ...additions,
      ]);
      setEdges((old) => [...old, ...connections]);
      setOmitted((old) => old + skipped);
    } catch (error) {
      if (mounted.current && !abort.signal.aborted && !context.retired)
        setNodes((old) =>
          old.map((n) =>
            n.key === node.key
              ? {
                  ...n,
                  error:
                    error instanceof Error ? error.message : 'Lookup failed',
                }
              : n,
          ),
        );
    } finally {
      if (mounted.current) setBusy('');
    }
  }
  const placed = nodes.map((n, index) => ({
    ...n,
    x: 18 + n.depth * 260,
    y:
      18 +
      nodes.slice(0, index).filter((v) => v.depth === n.depth).length * 150,
  }));
  const width = Math.max(260, ...placed.map((n) => n.x + 240)),
    height = Math.max(190, ...placed.map((n) => n.y + 138));
  const ancestry = new Set<string>();
  if (selected) {
    const stack = [selected.from];
    while (stack.length) {
      const key = stack.pop()!;
      if (ancestry.has(key)) continue;
      ancestry.add(key);
      edges.filter((e) => e.to === key).forEach((e) => stack.push(e.from));
    }
    ancestry.add(selected.to);
  }
  return (
    <section className="relations-explorer">
      <div className="graph-toolbar">
        <button onClick={() => setMode(mode === 'graph' ? 'list' : 'graph')}>
          {mode === 'graph' ? 'Show relation list' : 'Show graph'}
        </button>
        <button
          disabled={!!busy}
          onClick={() => {
            setNodes([initial]);
            setEdges([]);
            setOmitted(0);
            setSelected(null);
            setPage(0);
            setPan({ x: 0, y: 0 });
            setZoom(1);
          }}
        >
          Reset to selected record
        </button>
      </div>
      <p className="scope-note">
        Supplied fields only. Expand explicitly. Limits: 3 levels, 24 nodes, 80
        edges. Overall relationship completeness is unknown; missing edges do
        not prove absence.
      </p>
      {root.archived && (
        <p className="preview-note">
          Historical references are not current evidence. Current Work, Runs,
          Evidence and Knowledge destinations are current projections, not
          historical snapshots.
        </p>
      )}
      {(omitted > 0 || nodes.some((n) => n.loaded?.truncated)) && (
        <p className="preview-note">
          {omitted} supplied references omitted from this graph.{' '}
          {nodes.some((n) => n.loaded?.truncated)
            ? 'A supplied child/annotation collection is truncated. '
            : ''}
          Use the relation list and source record pagination.
        </p>
      )}
      {mode === 'graph' ? (
        <>
          <div className="graph-toolbar">
            <button onClick={() => setZoom((z) => Math.max(0.2, z - 0.15))}>
              Zoom out
            </button>
            <output>{Math.round(zoom * 100)}%</output>
            <button onClick={() => setZoom((z) => Math.min(1.6, z + 0.15))}>
              Zoom in
            </button>
            <button
              onClick={() => {
                setZoom(
                  Math.min(1, (viewport.current?.clientWidth ?? width) / width),
                );
                setPan({ x: 0, y: 0 });
              }}
            >
              Fit to width
            </button>
            <button
              onClick={() => {
                setZoom(1);
                setPan({ x: 0, y: 0 });
              }}
            >
              Reset zoom
            </button>
          </div>
          <div
            className="provenance-viewport"
            tabIndex={0}
            aria-label="Provenance graph canvas"
            ref={viewport}
            onPointerDown={(e) => {
              if ((e.target as HTMLElement).closest('button,a')) return;
              drag.current = {
                x: e.clientX,
                y: e.clientY,
                px: pan.x,
                py: pan.y,
              };
              e.currentTarget.setPointerCapture(e.pointerId);
            }}
            onPointerMove={(e) => {
              if (drag.current)
                setPan({
                  x: drag.current.px + e.clientX - drag.current.x,
                  y: drag.current.py + e.clientY - drag.current.y,
                });
            }}
            onPointerUp={() => {
              drag.current = null;
            }}
            onPointerCancel={() => {
              drag.current = null;
            }}
            onKeyDown={(e) => {
              if (e.target !== e.currentTarget) return;
              const delta: Record<string, [number, number]> = {
                ArrowLeft: [36, 0],
                ArrowRight: [-36, 0],
                ArrowUp: [0, 36],
                ArrowDown: [0, -36],
              };
              if (delta[e.key]) {
                e.preventDefault();
                const [x, y] = delta[e.key];
                setPan((p) => ({ x: p.x + x, y: p.y + y }));
              }
            }}
          >
            <div
              className="provenance-plane"
              ref={(el) => {
                if (el) {
                  el.style.width = width + 'px';
                  el.style.height = height + 'px';
                  el.style.transform = `translate(${pan.x}px,${pan.y}px) scale(${zoom})`;
                }
              }}
            >
              <svg
                width={width}
                height={height}
                aria-label="Supplied relations"
                role="img"
              >
                {edges.map((edge) => {
                  const a = placed.find((n) => n.key === edge.from)!,
                    b = placed.find((n) => n.key === edge.to)!;
                  return (
                    <line
                      key={edge.key}
                      x1={a.x + 220}
                      y1={a.y + 65}
                      x2={b.x}
                      y2={b.y + 65}
                      className={
                        selected?.key === edge.key ? 'selected-edge' : ''
                      }
                    />
                  );
                })}
              </svg>
              {placed.map((node) => (
                <section
                  key={node.key}
                  className={
                    'provenance-node' +
                    (ancestry.has(node.key) ? ' highlighted' : '')
                  }
                  ref={(el) => {
                    if (el) {
                      el.style.left = node.x + 'px';
                      el.style.top = node.y + 'px';
                    }
                  }}
                >
                  <strong>
                    <code>{node.id}</code>
                  </strong>
                  <span>{node.kind}</span>
                  <EntityAnchor entity={{ id: node.id, kind: node.kind }} />
                  {node.depth < limits.depth &&
                  (node.loaded || allowed(node)) ? (
                    <button
                      disabled={!!busy || node.expanded}
                      onClick={() => void expand(node)}
                    >
                      {node.expanded
                        ? 'Expanded'
                        : node.error
                          ? 'Retry expansion'
                          : 'Expand ' + node.id}
                    </button>
                  ) : (
                    <small>
                      {node.depth >= limits.depth
                        ? 'Depth limit'
                        : 'Terminal / unavailable reference'}
                    </small>
                  )}
                  {node.error && <small role="alert">{node.error}</small>}
                </section>
              ))}
            </div>
          </div>
          <ul className="graph-edge-list">
            {edges.map((e) => (
              <li key={e.key}>
                <button onClick={() => setSelected(e)}>
                  {e.source.id} · {e.relation.field} · {e.relation.target.id}
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
          <p>
            {allRelations.length} references from loaded records; no crawl or
            completeness claim.
          </p>
          <ul className="relation-list">
            {allRelations.slice(page * 100, (page + 1) * 100).map((e) => (
              <li key={e.key}>
                <button onClick={() => setSelected(e)}>
                  {e.source.id} · {e.relation.field}
                </button>{' '}
                <EntityAnchor entity={e.relation.target} />
              </li>
            ))}
          </ul>
          <div className="pagination">
            <button disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
              Previous relations
            </button>
            <button
              disabled={(page + 1) * 100 >= allRelations.length}
              onClick={() => setPage((p) => p + 1)}
            >
              Next relations
            </button>
          </div>
          {nodes
            .filter(
              (n) =>
                !n.expanded &&
                n.depth < limits.depth &&
                (n.loaded || allowed(n)),
            )
            .map((n) => (
              <button
                key={n.key}
                disabled={!!busy}
                onClick={() => void expand(n)}
              >
                Expand {n.id}
              </button>
            ))}
        </>
      )}
      {selected && (
        <section className="edge-inspection">
          <h3>Supplied edge source</h3>
          <p>
            <code>{selected.source.id}</code> /{' '}
            <code>{selected.relation.field}</code> /{' '}
            <code>{selected.relation.target.id}</code>
          </p>
          <SourceStrip source={selected.source.source} />
          <p>
            No edge-specific explanation or receipt supplied. Highlight shows
            browser connectivity among loaded links only.
          </p>
        </section>
      )}
    </section>
  );
}
