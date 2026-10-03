import version from './contract-version.json';
export type ReadIdentity = {
  mode: 'live' | 'demo';
  dataset: string;
  contract: string;
  snapshot: string;
  authorization_generation: string;
};
export const liveIdentity: ReadIdentity = {
  mode: 'live',
  dataset: 'same-origin',
  contract: `accepted:${version.version}:${version.sha256}`,
  snapshot: 'live',
  authorization_generation: 'initial',
};
let serial = 0;
export class ReadContext {
  readonly generation = ++serial;
  private project?: string;
  private active = true;
  constructor(readonly identity: ReadIdentity = liveIdentity) {
    this.identity = Object.freeze({ ...identity });
  }
  get projectId() {
    return this.project;
  }
  get retired() {
    return !this.active;
  }
  bind(project: string) {
    if (this.project !== undefined && this.project !== project)
      throw new Error('Projection belongs to a different project');
    this.project = project;
  }
  retire() {
    this.active = false;
  }
  key(route: string) {
    return JSON.stringify([
      this.identity.mode,
      this.identity.dataset,
      this.identity.contract,
      route === '/project' ? 'bootstrap' : (this.project ?? 'unbound'),
      this.identity.snapshot,
      this.identity.authorization_generation,
      this.generation,
    ]);
  }
}

export function reconciliationGroup(key: unknown, project: string) {
  try {
    const parts = JSON.parse(String(key));
    if (Array.isArray(parts)) {
      parts[3] = project;
      return JSON.stringify(parts);
    }
  } catch {
    /* Foreign query keys do not share a context. */
  }
  return `${String(key)}:${project}`;
}
