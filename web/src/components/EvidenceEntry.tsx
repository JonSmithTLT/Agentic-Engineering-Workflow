import { Link,useLocation } from 'react-router-dom';
import { useLayoutEffect,useRef } from 'react';
import { navigationParams } from '../api/navigation';
import { rememberReference,returnPosition,restoreReference } from './reference-return';
export function EvidenceEntry({id}:{id?:string}){
  const location=useLocation(),element=useRef<HTMLAnchorElement>(null),restored=useRef(false),key=`evidence-entry:${id??'all'}`;
  useLayoutEffect(()=>{const p=returnPosition(location.state);if(!restored.current&&p&&p.reference===key&&element.current){restoreReference(p,element.current);restored.current=true;}},[location.state,key]);
  if(import.meta.env.MODE!=='demo')return null;
  const p=navigationParams(new URLSearchParams(location.search));if(id)p.set('evidence_filter',id);
  return <Link ref={element} className="button" state={{evidenceReturn:true}} onClick={event=>{if(event.button===0&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&!event.altKey)rememberReference(key);}} to={`/evidence/inspect?${p}`}>Inspect evidence</Link>;
}
