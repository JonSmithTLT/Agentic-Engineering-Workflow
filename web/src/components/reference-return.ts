import { focusBelowHeader } from './InvestigationTabs';
type ReturnPosition={url:string;reference:string;scroll:number};
export function returnPosition(state:unknown):ReturnPosition|undefined{const p=(state as {contextReturn?:ReturnPosition}|null)?.contextReturn;if(p&&p.url===window.location.pathname+window.location.search&&typeof p.reference==='string'&&Number.isFinite(p.scroll)&&p.scroll>=0)return p;}
/** Store presentation position only, never a payload or authorization token. */
export function rememberReference(reference:string){const s=window.history.state;window.history.replaceState({...s,usr:{...s?.usr,contextReturn:{url:window.location.pathname+window.location.search,reference,scroll:window.scrollY}}},'');}
export function restoreReference(p:ReturnPosition,element:HTMLElement){window.scrollTo({top:p.scroll,behavior:'instant'});focusBelowHeader(element);}
