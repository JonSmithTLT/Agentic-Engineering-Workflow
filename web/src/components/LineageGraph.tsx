import type { z } from 'zod';
import { historyDetail } from '../api/schema';
import { investigate, type Source } from '../client/investigation-model';
import { RelationsExplorer } from './RelationsExplorer';
export function LineageGraph({
  record,
  projection,
}: {
  record: z.infer<typeof historyDetail>;
  projection?: Source;
}) {
  return projection ? (
    <RelationsExplorer root={investigate('history', record, projection)} />
  ) : (
    <p>No validated source projection supplied.</p>
  );
}
