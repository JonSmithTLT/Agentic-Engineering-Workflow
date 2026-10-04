import { focusBelowHeader } from '../../../components/InvestigationTabs';
type ReturnPosition = { url: string; reference: string; scroll: number };
export function returnPosition(state: unknown): ReturnPosition | undefined {
  const position = (state as { contextReturn?: ReturnPosition } | null)?.contextReturn;
  if (position && position.url === window.location.pathname + window.location.search && typeof position.reference === 'string' && Number.isFinite(position.scroll) && position.scroll >= 0) return position;
}
/** Store presentation position on the departing history entry, never payloads. */
export function rememberReference(reference: string) {
  const state = window.history.state;
  window.history.replaceState({ ...state, usr: { ...state?.usr, contextReturn: { url: window.location.pathname + window.location.search, reference, scroll: window.scrollY } } }, '');
}
export function restoreReference(position: ReturnPosition, element: HTMLElement) {
  window.scrollTo({ top: position.scroll, behavior: 'instant' });
  focusBelowHeader(element);
}
