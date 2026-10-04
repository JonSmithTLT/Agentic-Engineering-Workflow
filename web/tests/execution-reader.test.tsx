import {it,expect} from 'vitest';
import {render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {useExecutionPage} from '../src/api/preview/execution/session';
import {ReadTransport} from '../src/api/transport';
import {ExecutionProjector,executionBase} from '../src/api/preview/execution/projector';
import {executionSchemas} from '../src/api/preview/execution/schema';
import {projectionKey} from '../src/client/queries';
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
