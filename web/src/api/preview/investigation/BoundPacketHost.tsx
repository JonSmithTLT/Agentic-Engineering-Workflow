import { useComparisonSource } from './session';
import { PacketInspector } from './PacketInspector';
import type { PacketSourceBinding } from './schema';
import type { ReactNode } from 'react';

/** Domain host: exact supplied source ownership, independent of the calling workspace. */
export function BoundPacketHost({ owner, name, binding, back, backLabel, render }: {
  owner: string; name: string; binding: PacketSourceBinding; back: () => void; backLabel: string;
  render?: (query: ReturnType<typeof useComparisonSource>) => ReactNode;
}) {
  const query = useComparisonSource(owner, name, binding.source_id, false, true, binding);
  if (render) return render(query);
  return <PacketInspector query={query} packetId={binding.record_id} name={name} back={back} backLabel={backLabel} />;
}
