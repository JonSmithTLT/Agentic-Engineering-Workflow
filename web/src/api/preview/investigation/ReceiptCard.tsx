import { SemanticValue } from '../../../components/States';
import { ContextReferences } from './ContextReferences';
import { knownReceiptTypes, knownReceiptStates, type Receipt } from './schema';
/** Supplied receipt presentation; no inference from packet preparation or citations. */
export function ReceiptCard({ receipt: r }: { receipt: Receipt }) {
  return <article className="receipt-card"><h4><code>{r.id}</code> · <SemanticValue value={r.type} known={knownReceiptTypes} /> · <SemanticValue value={r.state} known={knownReceiptStates} /></h4>
    <p>{r.result ?? 'No result text supplied.'}</p><p>Packet {r.packet_id} · Source {r.source_id} · Invocation {r.invocation_id} · Run {r.run_id ?? 'Not supplied'} · Snapshot {r.snapshot_id ?? 'Current'} · <time>{r.at ?? 'Timestamp not supplied'}</time></p>
    <ContextReferences values={r.provenance} />
  </article>;
}
