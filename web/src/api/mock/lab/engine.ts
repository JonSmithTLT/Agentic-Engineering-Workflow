import {
  type ReadClock,
  notifyReadClock,
  setReadClock,
} from '../../../client/clock';
import { requestLog } from '../../diagnostics';
import { transport } from '../../transport';
import { queryClient, resetReadSession } from '../../../client/queries';
import { DemoProjector, representationTag } from '../projector';
import type { World } from '../types';
import type { Recipe, ReplayAction } from './catalog';
import { scenarioVersion } from './config';
type Effect = Extract<ReplayAction, { kind: 'refresh' }>['effect'];
export type HarnessResponse = {
  status: number;
  body?: unknown;
  etag?: string;
  network?: boolean;
};
export class ReplayEngine {
  private listeners = new Set<() => void>();
  private version = 0;
  private ordinals = new Map<string, number>();
  private overrides = new Map<string, { ordinal: number; effect: Effect }>();
  private held: {
    id: number;
    resolve: () => void;
    session: number;
    route: string;
  }[] = [];
  private messages: string[] = [];
  private events: string[] = [];
  private milliseconds = 0;
  private visible = true;
  private step = 0;
  private serial = 0;
  private revision = '42';
  private mixed = false;
  private project = 'demo-aew';
  private workUnavailable = false;
  private server: DemoProjector;
  private epoch = 0;
  busy = false;
  constructor(
    readonly recipe: Recipe,
    readonly seed: number,
    private world: World,
  ) {
    this.world = structuredClone(world);
    this.server = new DemoProjector(this.world);
    const original = this.world.responses['/project'] as {
      project_id: string;
      control_revision: string;
    };
    this.project = original.project_id;
    this.revision = original.control_revision;
  }
  snapshot = () => this.version;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private changed() {
    this.version++;
    for (const listener of this.listeners) listener();
  }
  get state() {
    return {
      step: this.step,
      pending: this.held.map(({ id, route, session }) => ({
        id,
        route,
        session,
      })),
      diagnostics: this.messages,
      events: this.events,
      milliseconds: this.milliseconds,
      visible: this.visible,
      busy: this.busy,
    };
  }
  private clock: ReadClock = {
    manual: true,
    now: () => new Date(Date.parse('2026-10-03T12:00:00Z') + this.milliseconds),
    monotonic: () => this.milliseconds,
    visible: () => this.visible && document.visibilityState === 'visible',
    subscribe: () => () => {},
  };
  async start() {
    setReadClock(this.clock);
    await resetReadSession({
      ...transport.context.identity,
      mode: 'demo',
      dataset: `${this.world.fixture}:${scenarioVersion}:${this.recipe.id}:${this.seed}`,
      authorization_generation: `replay-${this.epoch}`,
    });
  }
  async reset() {
    this.epoch++;
    this.step = 0;
    this.milliseconds = 0;
    this.visible = true;
    this.ordinals.clear();
    this.overrides.clear();
    this.messages = [];
    this.events = [];
    this.busy = false;
    this.server = new DemoProjector(this.world);
    this.workUnavailable = false;
    this.mixed = false;
    const original = this.world.responses['/project'] as {
      project_id: string;
      control_revision: string;
    };
    this.project = original.project_id;
    this.revision = original.control_revision;
    await this.start();
    for (const pending of this.held) pending.resolve();
    this.held = [];
    this.changed();
    notifyReadClock();
  }
  private record(message: string) {
    this.events = [...this.events, message].slice(-100);
    this.changed();
  }
  async respond(request: Request): Promise<HarnessResponse> {
    const url = new URL(request.url),
      route = url.pathname.slice('/api/v1'.length) + url.search;
    const ordinal = (this.ordinals.get(route) ?? 0) + 1;
    this.ordinals.set(route, ordinal);
    const assignment = this.overrides.get(route);
    let effect: Effect = 'normal';
    if (assignment && assignment.ordinal === ordinal) {
      effect = assignment.effect;
      this.overrides.delete(route);
    } else if (this.busy || ordinal > 1) {
      this.messages = [
        ...this.messages,
        `Unmatched harness request ${route} #${ordinal}; expected ${assignment ? '#' + assignment.ordinal : 'an explicitly scheduled route'}. Extra requests may require recipe updates.`,
      ].slice(-100);
    }
    if (ordinal === 1 && route === '/project') {
      if (this.recipe.id === 'initial-304') effect = 'initial304';
      if (this.recipe.id === 'initial-http') effect = 'http';
      if (this.recipe.id === 'initial-network') effect = 'network';
    }
    const capturedSession = transport.context.generation;
    const result = this.server.read(url);
    const body = structuredClone(result.body) as
      | Record<string, unknown>
      | undefined;
    if (body) {
      body.project_id = this.project;
      if (
        url.pathname === '/api/v1/project' &&
        typeof body.data === 'object' &&
        body.data
      )
        (body.data as Record<string, unknown>).id = this.project;
      if (this.mixed && url.pathname === '/api/v1/project') {
        /* keep the original project revision */
      } else body.control_revision = this.revision;
      if (url.pathname === '/api/v1/capabilities' && this.workUnavailable)
        (body.data as Record<string, unknown>).work = {
          state: 'UNAVAILABLE',
          reasons: [
            { code: 'DEMO_DOWNGRADE', message: 'Authored fixture downgrade' },
          ],
        };
      if (
        effect === 'unknown' &&
        url.pathname.startsWith('/api/v1/work') &&
        typeof body.data === 'object' &&
        body.data
      ) {
        const data = body.data as {
          items?: Record<string, unknown>[];
          state?: string;
        };
        if (data.items?.[0]) data.items[0].state = 'W01_FUTURE_STATE';
        else data.state = 'W01_FUTURE_STATE';
      }
    }
    const tag = body ? await representationTag(url, body) : undefined;
    if (effect === 'hold') {
      await new Promise<void>((resolve) => {
        this.held.push({
          id: ++this.serial,
          resolve,
          session: capturedSession,
          route,
        });
        this.changed();
      });
    }
    if (capturedSession === transport.context.generation)
      this.record(`${route} #${ordinal}: ${effect} @ ${this.milliseconds}ms`);
    if (effect === 'network') return { status: 0, network: true };
    if (effect === 'http') return { status: 500 };
    if (effect === 'malformed')
      return { status: 200, body: { bad: 'projection' } };
    if (effect === 'initial304') return { status: 304 };
    if (effect === 'bad304')
      return { status: 304, etag: '"w01-anomalous-validator"' };
    if (result.status !== 200) return { status: result.status };
    if (request.headers.get('If-None-Match') === tag)
      return { status: 304, etag: tag };
    return { status: 200, body, etag: tag };
  }
  release(id: number) {
    const pending = this.held.find((p) => p.id === id);
    this.held = this.held.filter((p) => p.id !== id);
    pending?.resolve();
    this.changed();
  }
  async next() {
    const step = this.recipe.steps[this.step];
    if (!step || this.busy) return;
    this.busy = true;
    this.step++;
    this.changed();
    try {
      const action = step.action;
      if (action.kind === 'advance') {
        if (action.visible !== undefined) {
          this.visible = action.visible;
          notifyReadClock();
        }
        this.milliseconds += action.milliseconds;
        notifyReadClock();
        if (action.visible === true)
          await queryClient.refetchQueries({ type: 'active' });
      } else if (action.kind === 'switch') {
        this.project = 'demo-aew-other';
        await resetReadSession({
          ...transport.context.identity,
          authorization_generation: `switch-${++this.epoch}`,
        });
      } else {
        const effect = action.effect ?? 'normal';
        if (effect === 'downgrade') this.workUnavailable = true;
        if (effect === 'mixed') {
          this.mixed = true;
          this.revision = String(BigInt(this.revision) + 1n);
        }
        if (effect === 'converge') this.mixed = false;
        const queries = queryClient
          .getQueryCache()
          .findAll({ type: 'active', queryKey: ['projection'] });
        for (const query of queries) {
          const route = String(query.queryKey[2]);
          if (effect === 'hold' && route !== '/overview') continue;
          this.overrides.set(route, {
            ordinal: (this.ordinals.get(route) ?? 0) + 1,
            effect,
          });
        }
        const run = queryClient.refetchQueries({
          type: 'active',
          predicate: (q) => effect !== 'hold' || q.queryKey[2] === '/overview',
        });
        if (effect !== 'hold') await run;
        else void run;
      }
    } finally {
      this.busy = false;
      this.changed();
    }
  }
  /** Inspect only: no API meaning derives from these authored ordinals. */
  diagnostic(message: string) {
    this.messages = [...this.messages, message].slice(-100);
    this.changed();
  }
  clearLog() {
    requestLog.clear();
  }
}
