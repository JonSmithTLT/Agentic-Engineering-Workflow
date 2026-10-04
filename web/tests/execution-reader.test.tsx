import {it,expect} from 'vitest';
import {render,screen,waitFor,fireEvent} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {useExecutionPage} from '../src/api/preview/execution/session';
import {ReadTransport} from '../src/api/transport';
import {ExecutionProjector,executionBase} from '../src/api/preview/execution/projector';
import {executionSchemas} from '../src/api/preview/execution/schema';
import {projectionKey} from '../src/client/queries';
import {executionFixture} from '../src/api/preview/execution/fixtures';
import {FanoutHierarchy} from '../src/api/preview/execution/Fanout';
it('retries the failed child expansion rather than the already loaded root',async()=>{
 const projector=new ExecutionProjector(),calls:string[]=[],client=new QueryClient({defaultOptions:{queries:{retry:false}}});let fail=true;
 const reader=new ReadTransport(async(input)=>{const route=String(input);calls.push(route);if(route.includes('/executions/EX-Retry?')&&fail){fail=false;return new Response('',{status:503});}return new Response(JSON.stringify(projector.read(new URL(route,'http://demo.test')).body),{headers:{'Content-Type':'application/json'}});},undefined,undefined,{base:executionBase,routes:/^\/traces/});reader.context.bind('aew-demo');
 render(<QueryClientProvider client={client}><FanoutHierarchy trace={executionFixture().traces[0]} name="story" reader={reader} select={()=>{}}/></QueryClientProvider>);
 fireEvent.click(screen.getByRole('button',{name:'Expand EX-Removal'}));fireEvent.click(await screen.findByRole('button',{name:'Expand EX-Retry'}));await screen.findByRole('alert');fireEvent.click(screen.getByRole('button',{name:'Retry'}));await screen.findByRole('button',{name:'Expand EX-Helper'});
 expect(calls.filter(r=>r.includes('/executions/EX-Retry?'))).toHaveLength(2);expect(calls.filter(r=>r.includes('/executions/EX-Removal?'))).toHaveLength(1);
});
it('replaces cached result bodies/validators and makes no concealed page reads',async()=>{
 const projector=new ExecutionProjector(),calls:{route:string;validator:string|null}[]=[],client=new QueryClient({defaultOptions:{queries:{retry:false}}});
 const reader=new ReadTransport(async(input,init)=>{const route=String(input),validator=new Headers(init?.headers).get('If-None-Match');calls.push({route,validator});return new Response(JSON.stringify(projector.read(new URL(route,'http://demo.test')).body),{headers:{'Content-Type':'application/json',ETag:'"fixed"'}});},undefined,undefined,{base:executionBase,routes:/^\/traces/});reader.context.bind('aew-demo');
 function Probe({route,visible}:{route:string;visible:boolean}){const q=useExecutionPage(route,executionSchemas.EventListResponse,reader,visible);return <p>{q.data?.value.data.items[0]?.id??'Loading'}</p>;}
 const a='/traces/TRACE-Clangd/events?case=large',b='/traces/TRACE-Clangd/events?case=large&lane=context';
 const view=render(<QueryClientProvider client={client}><Probe route={a} visible={false}/></QueryClientProvider>);
 expect(calls).toHaveLength(0);view.rerender(<QueryClientProvider client={client}><Probe route={a} visible/></QueryClientProvider>);await screen.findByText('EV-01');
 view.rerender(<QueryClientProvider client={client}><Probe route={b} visible/></QueryClientProvider>);await screen.findByText('EV-05');await waitFor(()=>expect(client.getQueryData(projectionKey(a,reader))).toBeUndefined());expect(client.getQueryCache().findAll()).toHaveLength(1);
 view.rerender(<QueryClientProvider client={client}><Probe route={a} visible/></QueryClientProvider>);await screen.findByText('EV-01');expect(calls.at(-1)?.validator).toBeNull();expect(client.getQueryCache().findAll()).toHaveLength(1);view.unmount();expect(client.getQueryCache().findAll()).toHaveLength(0);
});
