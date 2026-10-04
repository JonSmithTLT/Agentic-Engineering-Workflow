import { useSearchParams } from 'react-router-dom';
import { LoadError } from '../../../components/States';
import { z } from 'zod';
export function useControls() {
  const [params, setParams] = useSearchParams();
  const update = (values: Record<string, string | null>, replace = false) => setParams(old => { const next = new URLSearchParams(old); for (const [key, value] of Object.entries(values)) { if (value) next.set(key, value); else next.delete(key); } return next; }, { replace });
  return { params, update };
}
export function ErrorState({ error, retry }: { error: unknown; retry: () => void }) {
  const message = error instanceof z.ZodError ? `Projection validation failed: ${error.issues.slice(0, 3).map(issue => issue.message).join('; ')}` : error instanceof Error ? error.message : 'Projection unavailable';
  return <LoadError message={message} retry={retry} />;
}
