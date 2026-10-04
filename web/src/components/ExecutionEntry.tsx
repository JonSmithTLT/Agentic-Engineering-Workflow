import { Link,useLocation } from 'react-router-dom';
import { lazy,Suspense } from 'react';
const Controls=import.meta.env.MODE==='demo'?lazy(()=>import('../api/preview/execution/Controls').then(m=>({default:m.ControlsDisclosure}))):null;
export function ExecutionEntry({invocation,run,displayed=true,discloseControls=true}:{invocation?:string;run?:string|null;displayed?:boolean;discloseControls?:boolean}){
 const location=useLocation();
 if(import.meta.env.MODE!=='demo')return null;
 const p=new URLSearchParams({fixture:new URLSearchParams(location.search).get('fixture')??'F1'});if(invocation)p.set('execution_invocation',invocation);if(run)p.set('execution_run',run);
 return <><Link to={`/execution?${p}`}>Inspect recorded execution</Link>{Controls&&invocation&&discloseControls&&<Suspense fallback={<p>Loading disclosed controls…</p>}><Controls invocation={invocation} run={run} displayed={displayed}/></Suspense>}</>;
}
