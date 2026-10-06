import {URL} from 'node:url';
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const out=process.env.W07_BROWSER_OUTPUT??'output/playwright-w07',ports={http:process.env.W07_HTTP_PORT??'4290',worker:process.env.W07_WORKER_PORT??'4291'};
fs.mkdirSync(out,{recursive:true});const children=[],checks=[],measurements=[];let browser;
function serve(mode){const log=fs.openSync(`${out}/${mode}-server.log`,'w');const child=spawn(process.execPath,mode==='http'?['--experimental-strip-types','scripts/demo-server.mjs']:['node_modules/vite/bin/vite.js','preview','--mode','demo','--host','127.0.0.1','--port',ports.worker,'--strictPort'],{env:{...process.env,DASHBOARD_PORT:ports.http},stdio:['ignore',log,log]});children.push(child);return child;}
async function ready(mode,child){for(let i=0;i<100;i++){if(child.exitCode!==null)throw Error(`Owned ${mode} server exited`);try{if((await globalThis.fetch(`http://127.0.0.1:${ports[mode]}`)).ok)return;}catch{/* Startup */}await new Promise(r=>globalThis.setTimeout(r,100));}throw Error('Server startup timeout');}
async function check(name,mode,run,phone=false){if(process.env.W07_BROWSER_FILTER&&!name.includes(process.env.W07_BROWSER_FILTER))return;const context=await browser.newContext({viewport:phone?{width:390,height:844}:{width:1440,height:1000},serviceWorkers:mode==='http'?'block':'allow',permissions:['clipboard-read','clipboard-write']}),page=await context.newPage(),requests=[],errors=[];page.on('request',r=>requests.push({url:r.url(),method:r.method(),etag:r.headers()['if-none-match']}));page.on('pageerror',e=>errors.push(e.message));await context.tracing.start({screenshots:true,snapshots:true});try{await run(page,`http://127.0.0.1:${ports[mode]}`,requests);assert.deepEqual(errors,[]);assert(requests.every(r=>['GET','HEAD'].includes(r.method)));if(mode==='http'){assert.equal(context.serviceWorkers().length,0);assert(!requests.some(r=>/mockServiceWorker|assets\/browser-/.test(r.url)));}checks.push({name,mode,phone,result:'PASS'});console.log(`PASS ${mode} ${phone?'phone':'desktop'} ${name}`);await context.tracing.stop();}catch(e){await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:`${out}/failure-${checks.length}.png`,fullPage:true});await context.tracing.stop({path:`${out}/failure-${checks.length}.zip`});throw e;}finally{await context.close();}}
const route='/knowledge?fixture=F1&view=journal&selected=J-05&panel=provenance';
try {
 const http=serve('http'),worker=serve('worker');await Promise.all([ready('http',http),ready('worker',worker)]);
 browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH??'artifacts/playwright/browsers/chromium-1217/chrome-linux64/chrome',headless:true,args:['--no-sandbox']});
 for(const mode of ['http','worker'])for(const phone of [false,true])await check('Supplied Journal association, distinct receipts, copy/reload and restored origin',mode,async(page,base,requests)=>{
  await page.goto(base+route);await page.getByText('Context associations',{exact:true}).click();
  const link=page.getByRole('button',{name:'Inspect associated packet PKT-Later'});await link.waitFor();
  assert(!requests.some(r=>r.url.includes('/api/preview/investigation/')),'Disclosure must not read packets');
  const journalNodes=await page.locator('*').count(), journalRequests=requests.filter(r=>r.url.includes('/api/preview/')).length;
  await link.click();await page.getByRole('heading',{name:'Context packet PKT-Later'}).waitFor();
  await page.getByRole('heading',{name:'J-05 · recall',exact:true}).waitFor();
  await page.getByRole('tab',{name:'Selection & budget',exact:true}).click();
  await page.getByRole('link',{name:'J-05',exact:true}).click();
  await page.getByRole('heading',{name:/J-05 · Refresh compile/}).waitFor();
  await page.goBack();await page.getByRole('heading',{name:'Context packet PKT-Later'}).waitFor();
  await page.getByRole('tab',{name:'Receipts',exact:true}).click();
  await page.getByText('RECEIPT-Later-DELIVERY',{exact:true}).waitFor();
  await page.getByText('No benefit evaluation supplied.',{exact:true}).waitFor();
  measurements.push({mode,phone,journalNodes,journalRequests,inspectorNodes:await page.locator('*').count(),investigationRequests:requests.filter(r=>r.url.includes('/api/preview/investigation/')).length,loadedItemPanels:await page.locator('.packet-items > li').count(),scope:'One explicitly supplied association; validation page is discarded before inspector. Receipt tab has no displayed item page. Not a timing SLA or complete backend reuse index.'});
  const before=requests.filter(r=>r.url.includes('/api/preview/journal/')).length;
  await page.waitForTimeout(11000);assert.equal(requests.filter(r=>r.url.includes('/api/preview/journal/')).length,before);
  await page.getByRole('tab',{name:'Provenance',exact:true}).click();await page.getByText('CLANGD-D42',{exact:true}).waitFor();
  await page.screenshot({path:`${out}/${mode}-${phone?'phone':'desktop'}-packet.png`,fullPage:true});
  await page.getByRole('button',{name:'Copy dashboard link',exact:true}).click();const copied=await page.evaluate(()=>navigator.clipboard.readText());
  assert.equal(new URL(copied).searchParams.get('context_association'),'ASSOC-J05-Later');
  await page.getByRole('button',{name:'Back to Journal',exact:true}).click();
  await page.waitForFunction(()=>document.activeElement?.getAttribute('data-context-association')==='ASSOC-J05-Later');
  await page.screenshot({path:`${out}/${mode}-${phone?'phone':'desktop'}-journal.png`,fullPage:true});
  await page.goto(copied);await page.getByRole('heading',{name:'Context packet PKT-Later'}).waitFor();
  await page.getByRole('tab',{name:'Provenance',exact:true}).waitFor();
  await page.getByRole('button',{name:'Back to Journal',exact:true}).click();await page.getByText('Context associations',{exact:true}).waitFor();
 },phone);
 await check('Exact originating case and item mismatch refuse substitution','http',async(page,base,requests)=>{
  await page.goto(base+route+'&journal_case=missing&context_association=ASSOC-J05-Later');await page.getByRole('alert').first().waitFor();assert(!requests.some(r=>r.url.includes('/api/preview/investigation/')));
  await page.route('**/api/preview/investigation/**/items?**',async r=>{const response=await r.fetch({headers:{...r.request().headers(),'if-none-match':''}});const body=await response.json();for(const item of body.data.items)item.reference.id='J-04';await r.fulfill({response,json:body});});
  await page.goto(base+route+'&context_association=ASSOC-J05-Later');await page.getByRole('alert').first().waitFor();assert.equal(await page.getByRole('heading',{name:'Context packet PKT-Later'}).count(),0);
 });
 await check('Denied item page hides inspector and permits refusal recovery','http',async(page,base)=>{
  await page.route('**/api/preview/investigation/**/items?**',r=>r.fulfill({status:403,body:'hidden title and excerpt'}));
  await page.goto(base+route+'&context_association=ASSOC-J05-Later');await page.getByRole('alert').first().waitFor();assert.equal(await page.getByText('hidden title and excerpt').count(),0);assert.equal(await page.getByRole('heading',{name:'Context packet PKT-Later'}).count(),0);
  await page.unroute('**/api/preview/investigation/**/items?**');await page.getByRole('button',{name:/Retry/}).first().click();await page.getByRole('heading',{name:'Context packet PKT-Later'}).waitFor();
 });
 fs.writeFileSync(`${out}/report.json`,JSON.stringify({checks,measurements},null,2)+'\n');
} finally {await browser?.close();for(const child of children)child.kill();}
