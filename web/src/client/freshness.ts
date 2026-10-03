export type Check = { revision: string; failed: boolean };
export type SnapshotState =
  | 'CURRENT'
  | 'UPDATING'
  | 'STALE / DISCONNECTED'
  | 'LOAD ERROR'
  | 'LOADING';
export function snapshotState(
  checks: Check[],
  initialFailure = false,
): SnapshotState {
  if (!checks.length) return initialFailure ? 'LOAD ERROR' : 'LOADING';
  if (initialFailure || checks.some((c) => c.failed))
    return 'STALE / DISCONNECTED';
  return new Set(checks.map((c) => c.revision)).size > 1
    ? 'UPDATING'
    : 'CURRENT';
}
/** Accumulates visible divergence time; no inference about backend integrity. */
export class MixedRevisionClock {
  private elapsed = 0;
  private previous: number | undefined;
  private wasVisible = false;
  sample(mixed: boolean, visible: boolean, now: number) {
    if (!mixed) {
      this.elapsed = 0;
      this.previous = undefined;
      this.wasVisible = false;
      return false;
    }
    if (this.previous !== undefined && this.wasVisible)
      this.elapsed += Math.max(0, now - this.previous);
    this.previous = now;
    this.wasVisible = visible;
    return this.elapsed >= 30000;
  }
}
