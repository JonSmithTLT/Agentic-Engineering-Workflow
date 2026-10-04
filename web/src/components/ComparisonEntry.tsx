import { Link, useLocation } from 'react-router-dom';
import { navigationParams } from '../api/navigation';
export function ComparisonEntry({ work, invocation }: { work?: string; invocation?: string }) {
  const location = useLocation();
  if (import.meta.env.MODE !== 'demo') return null;
  const params = navigationParams(new URLSearchParams(location.search));
  if (work) params.set('compare_work', work);
  if (invocation) params.set('a_invocation', invocation);
  params.set('choose', 'a');
  return <Link className="button" to={`/compare?${params}`}>Compare invocations</Link>;
}
