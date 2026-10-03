import { readClock } from '../client/clock';
import { capabilityNames } from '../api/schema';
import { useEffect, useRef, useState } from 'react';
import {
  MixedRevisionClock,
  snapshotState,
  type Check,
} from '../client/freshness';
export function SnapshotBanner({
  checks,
  initialFailure = false,
}: {
  checks: Check[];
  initialFailure?: boolean;
}) {
  const state = snapshotState(checks, initialFailure);
  const mixed = state === 'UPDATING';
  const clock = useRef(new MixedRevisionClock());
  const [persistent, setPersistent] = useState(false);
  useEffect(() => {
    const tick = () =>
      setPersistent(
        clock.current.sample(mixed, readClock.visible(), readClock.monotonic()),
      );
    tick();
    const timer = readClock.manual ? undefined : window.setInterval(tick, 1000);
    const dispose = readClock.subscribe(tick);
    return () => {
      if (timer !== undefined) window.clearInterval(timer);
      dispose();
    };
  }, [mixed]);
  return (
    <div
      className={`snapshot ${state === 'CURRENT' ? 'current' : 'notice'}`}
      role="status"
    >
      <strong>{state}</strong>
      {persistent && mixed ? (
        <span>
          Mixed revisions persist. Visible projections have differed for at
          least 30 seconds of visible time.
        </span>
      ) : state === 'UPDATING' ? (
        <span>Visible projections are converging.</span>
      ) : state === 'STALE / DISCONNECTED' ? (
        <span>Latest refresh failed. Displaying last-known-good data.</span>
      ) : state === 'LOAD ERROR' ? (
        <span>No valid data has been loaded.</span>
      ) : null}
    </div>
  );
}
export function SemanticValue({
  value,
  known,
}: {
  value: string | null;
  known: readonly string[];
}) {
  if (value === null) return <span className="muted">Not supplied</span>;
  return known.includes(value) ? (
    <span className="tag">{value.replaceAll('_', ' ')}</span>
  ) : (
    <span className="unknown" role="status">
      Unknown value: <code>{value}</code>
    </span>
  );
}
export function Unavailable({ explanation }: { explanation: string }) {
  return (
    <div className="empty">
      <h2>Data unavailable</h2>
      <p>{explanation}</p>
    </div>
  );
}
export function LoadError({
  message,
  retry,
}: {
  message: string;
  retry: () => void;
}) {
  return (
    <div className="empty" role="alert">
      <h2>Could not load this projection</h2>
      <p>{message}</p>
      <button onClick={retry}>Retry</button>
    </div>
  );
}

export function CapabilityWarnings({
  values,
}: {
  values: Record<
    string,
    { state: string; reasons: { code: string; message: string | null }[] }
  >;
}) {
  const names: readonly string[] = capabilityNames;
  const states = ['AVAILABLE', 'UNAVAILABLE', 'UNSUPPORTED', 'UNKNOWN'];
  return (
    <>
      {Object.entries(values)
        .filter(
          ([name, value]) =>
            !names.includes(name) || !states.includes(value.state),
        )
        .map(([name, value]) => (
          <div className="preview-note" role="status" key={name}>
            {!names.includes(name)
              ? 'Unknown capability'
              : 'Unknown capability state'}
            : <code>{name}</code> · <code>{value.state}</code>
            {value.reasons.map((r, i) => (
              <p key={i}>{r.message ?? r.code}</p>
            ))}
          </div>
        ))}
    </>
  );
}
