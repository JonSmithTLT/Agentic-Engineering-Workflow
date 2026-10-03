import { projectionKey } from '../client/queries';
import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { z } from 'zod';
import { responseSchemas, historyDetail } from '../api/schema';
import { transport, type Projection } from '../api/transport';
import { PageSnapshot, useCapability } from '../client/dashboard';
import { EntityAnchor } from './EntityAnchor';
import { SemanticValue } from './States';
import { historyLinkRelations } from '../api/vocabulary';
type History = z.infer<typeof historyDetail>;
type Node = {
  key: string;
  id: string;
  kind: string;
  depth: number;
  record?: History;
  projection?: Projection<{ control_revision: string; generated_at: string }>;
  expanded?: boolean;
  error?: string;
};
type Edge = { from: string; to: string; relation: string };
const keyOf = (kind: string, id: string) => kind + ':' + id;
function targetKind(relation: string) {
  return relation === 'invocations'
    ? 'invocation'
    : relation === 'evidence'
      ? 'evidence'
      : ['depends_on', 'moved_to', 'audit_finding'].includes(relation)
        ? 'history'
        : 'reference';
}
export function LineageGraph({
  record,
  projection,
}: {
  record: History;
  projection?: Projection<{ control_revision: string; generated_at: string }>;
}) {
  const root = keyOf('history', record.id);
  const [nodes, setNodes] = useState<Node[]>([
    { key: root, id: record.id, kind: 'history', depth: 0, record, projection },
  ]);
  const [edges, setEdges] = useState<Edge[]>([]),
    [busy, setBusy] = useState(''),
    [limited, setLimited] = useState(false);
  const available = useCapability('history').available;
  const client = useQueryClient(),
    mounted = useRef(true),
    controllers = useRef(new Set<AbortController>());
  useEffect(() => {
    mounted.current = true;
    const active = controllers.current;
    return () => {
      mounted.current = false;
      for (const c of active) c.abort();
    };
  }, []);
  async function expand(node: Node) {
    if (busy || node.depth >= 3 || node.expanded || !available) return;
    setBusy(node.key);
    const controller = new AbortController();
    controllers.current.add(controller);
    try {
      const route = `/history/${encodeURIComponent(node.id)}?annotations_limit=100`;
      const loaded = node.record
        ? undefined
        : await client.fetchQuery({
            queryKey: projectionKey(route),
            queryFn: () =>
              transport.get(
                route,
                responseSchemas.HistoryResponse,
                controller.signal,
              ),
          });
      const data = node.record ?? loaded!.value.data;
      const metadata = loaded ?? node.projection;
      if (!mounted.current) return;
      const additions: Node[] = [],
        connections: Edge[] = [];
      const known = new Set(nodes.map((n) => n.key));
      let omitted = false;
      for (const [relation, targets] of Object.entries(data.links))
        for (const id of targets) {
          const kind = targetKind(relation),
            key = keyOf(kind, id);
          if (!known.has(key)) {
            if (nodes.length + additions.length >= 24) {
              omitted = true;
              continue;
            }
            known.add(key);
            additions.push({ key, id, kind, depth: node.depth + 1 });
          }
          if (edges.length + connections.length >= 80) {
            omitted = true;
            continue;
          }
          connections.push({ from: node.key, to: key, relation });
        }
      setNodes((old) => [
        ...old.map((n) =>
          n.key === node.key
            ? {
                ...n,
                record: data,
                projection: metadata,
                expanded: true,
                error: undefined,
              }
            : n,
        ),
        ...additions,
      ]);
      setEdges((old) => [...old, ...connections]);
      if (omitted) setLimited(true);
    } catch (error) {
      if (mounted.current && !controller.signal.aborted)
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
      controllers.current.delete(controller);
      if (mounted.current) setBusy('');
    }
  }
  const placed = nodes.map((node, index) => ({
    ...node,
    x: 28 + node.depth * 286,
    y:
      28 +
      nodes.slice(0, index).filter((n) => n.depth === node.depth).length * 148,
  }));
  const height = Math.max(190, ...placed.map((n) => n.y + 136));
  return (
    <section className="panel lineage-panel">
      <div className="panel-heading">
        <h2>Historical link graph</h2>
        <span>Explicit expansion · up to 3 levels</span>
      </div>
      <PageSnapshot
        queries={nodes.flatMap((node) =>
          node.projection
            ? [
                {
                  data: node.projection,
                  isError: !!node.error,
                  error: node.error ? new Error(node.error) : null,
                },
              ]
            : [],
        )}
      />
      <button
        className="lineage-reset"
        disabled={!!busy}
        onClick={() => {
          setNodes([
            {
              key: root,
              id: record.id,
              kind: 'history',
              depth: 0,
              record,
              projection,
            },
          ]);
          setEdges([]);
          setLimited(false);
        }}
      >
        Reset graph to current record
      </button>
      <p className="scope-note">
        Backend links only. Expand one History record at a time. Dashed cards
        are references, not loaded records; Runs and Evidence open their
        existing detail views. Limits: 24 cards and 80 links. Archived records
        never become current evidence.
      </p>
      {limited && (
        <p className="preview-note">
          Graph limit reached. Some supplied references are omitted; use the
          record’s complete bounded link display for inspection.
        </p>
      )}
      <div
        className="lineage-canvas"
        tabIndex={0}
        aria-label="Historical link graph canvas"
      >
        <div
          className="lineage-surface"
          ref={(el) => {
            if (el) {
              el.style.width = '1140px';
              el.style.height = height + 'px';
            }
          }}
        >
          <svg
            width="1140"
            height={height}
            aria-hidden="true"
            className="graph-edges"
          >
            <defs>
              <marker
                id="lineage-arrow"
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
            {edges.map((edge, i) => {
              const a = placed.find((n) => n.key === edge.from)!,
                b = placed.find((n) => n.key === edge.to)!;
              const x = a.x + 236,
                y = a.y + 54;
              return (
                <path
                  key={i}
                  d={`M ${x} ${y} C ${x + 25} ${y}, ${b.x - 25} ${b.y + 54}, ${b.x} ${b.y + 54}`}
                  markerEnd="url(#lineage-arrow)"
                />
              );
            })}
          </svg>
          {placed.map((node) => (
            <article
              key={node.key}
              className={
                'lineage-card' + (node.record ? '' : ' reference-card')
              }
              ref={(el) => {
                if (el) {
                  el.style.left = node.x + 'px';
                  el.style.top = node.y + 'px';
                }
              }}
            >
              <code>{node.id}</code>
              <div>
                {node.kind === 'reference' ? (
                  <span>Reference only · no destination declared</span>
                ) : (
                  <EntityAnchor
                    entity={{
                      kind: node.kind,
                      id: node.id,
                      title: node.record?.title ?? node.id,
                    }}
                  />
                )}
              </div>
              <small>
                {node.record
                  ? 'Loaded historical record'
                  : 'Unloaded reference'}
                {node.projection && (
                  <> · rev {node.projection.value.control_revision}</>
                )}
              </small>
              {node.kind === 'history' && !node.expanded && node.depth < 3 && (
                <button
                  disabled={!!busy || !available}
                  onClick={() => {
                    void expand(node);
                  }}
                >
                  {busy === node.key
                    ? 'Loading…'
                    : node.error
                      ? 'Retry History lookup'
                      : 'Expand links'}
                </button>
              )}
              {node.error && (
                <span className="lineage-error" role="status">
                  History lookup failed; reference remains. {node.error}
                </span>
              )}
            </article>
          ))}
        </div>
      </div>
      <details className="lineage-relations">
        <summary>Link types and destinations</summary>
        <ul>
          {edges.map((edge, i) => (
            <li key={i}>
              <code>{nodes.find((n) => n.key === edge.from)?.id}</code> →{' '}
              <SemanticValue
                value={edge.relation}
                known={historyLinkRelations}
              />{' '}
              → <code>{nodes.find((n) => n.key === edge.to)?.id}</code>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
