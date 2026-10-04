import { Link,useLocation } from 'react-router-dom';
import { useLayoutEffect,useRef } from 'react';
import { findAssociation } from './fixtures';
import { rememberReference,returnPosition,restoreReference } from '../investigation/return-focus';
import type { Origin } from './schema';
import { navigationParams } from '../../navigation';
/** Exact fixture-supplied association; canonical Evidence ID never substitutes for it. */
export function EvidenceReference({origin,children}:{origin:Origin;children:React.ReactNode}){
  const a=findAssociation(origin),location=useLocation(),element=useRef<HTMLAnchorElement>(null),restored=useRef(false);
  useLayoutEffect(()=>{const position=returnPosition(location.state);if(!restored.current&&position&&position.reference===a?.reference_id&&element.current&&element.current.getClientRects().length){restoreReference(position,element.current);restored.current=true;}});
  if(!a)return <>{children} <small>(Evidence reference; no inspection mapping supplied)</small></>;
  const p=navigationParams(new URLSearchParams(location.search));p.set('evidence_reference',a.reference_id);p.set('evidence_case','story');
  return <Link ref={element} state={{evidenceReturn:true}} data-evidence-reference={a.reference_id} to={`/evidence/inspect?${p}`} onClick={event=>{if(event.button===0&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&!event.altKey)rememberReference(a.reference_id);}}>{children}</Link>;
}
