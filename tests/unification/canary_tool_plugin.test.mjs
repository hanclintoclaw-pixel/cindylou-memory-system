import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import fs from 'node:fs';
import {PassThrough} from 'node:stream';
import test from 'node:test';
import plugin,{createTool,NAME} from '../../integrations/openclaw-memory-canary/index.mjs';

const context=()=>({assertInvocationCurrent(){},sandboxed:false});
const config={enabled:true,tokenFile:'/private/token',port:18091};
function synthetic(status='ok') {
  const details={version:1,status,results:[],coverage:'partial',
    caller:{audience:'public',domain:'campaign',production_integration:false}};
  return {content:[{type:'text',text:JSON.stringify(details)}],details,isError:status!=='ok'};
}
function fakeSpawn(result=synthetic(),exit=0) {
  const calls=[];
  const spawn=(python,args,options)=>{
    const child=new EventEmitter();
    child.stdout=new PassThrough();
    child.stdin=new PassThrough();
    child.kill=signal=>{calls.push({signal});queueMicrotask(()=>child.emit('close',null));};
    calls.push({python,args,options,child});
    child.stdin.on('finish',()=>queueMicrotask(()=>{
      if (result!==null) {child.stdout.emit('data',Buffer.from(JSON.stringify(result)));child.emit('close',exit);}
    }));
    return child;
  };
  return {spawn,calls};
}

test('manifest/registration align and optional v2 factory does not perform I/O',()=>{
  const manifest=JSON.parse(fs.readFileSync(new URL('../../integrations/openclaw-memory-canary/openclaw.plugin.json',import.meta.url)));
  let registered;
  plugin.register({pluginConfig:{},registerTool(factory,options){registered={factory,options};}});
  assert.equal(registered.factory.contextVersion,2);
  assert.deepEqual(registered.options,{name:NAME,optional:true});
  assert.deepEqual(manifest.contracts.tools,[NAME]);
  assert.equal(manifest.toolMetadata[NAME].optional,true);
  assert.equal(manifest.configSchema.properties.enabled.default,false);
});

test('disabled and invalid trusted config never spawn',async()=>{
  const fake=fakeSpawn();
  const disabled=await createTool({},context(),fake.spawn).execute('id',{operation:'health'});
  assert.equal(disabled.details.status,'disabled');
  const invalid=await createTool({...config,tokenFile:'relative'},context(),fake.spawn).execute('id',{operation:'health'});
  assert.equal(invalid.details.status,'unavailable');
  assert.equal(fake.calls.length,0);
});

test('sandbox and absent invocation currency guard cannot construct tool',()=>{
  assert.equal(createTool(config,{...context(),sandboxed:true}),null);
  assert.equal(createTool(config,{}),null);
});

test('wrapper forwards unchanged evidence to tool output with fixed isolated interpreter',async()=>{
  const fake=fakeSpawn();
  const result=await createTool(config,context(),fake.spawn).execute('id',{operation:'health'});
  assert.deepEqual(result,synthetic());
  const call=fake.calls[0];
  assert.equal(call.python,'/opt/homebrew/opt/python@3.14/bin/python3.14');
  assert.equal(call.args[0],'-I');
  assert.ok(call.args.includes('--enable-canary'));
  assert.equal(call.options.cwd,'/');
  assert.deepEqual(call.options.stdio,['pipe','pipe','ignore']);
  assert.equal(call.args.includes('PRIVATE TOKEN VALUE'),false);
});

test('exit-code or content-details mismatch fails closed',async()=>{
  for (const [result,exit] of [[synthetic(),5],[{...synthetic(),content:[{type:'text',text:'{}'}]},0]]) {
    const fake=fakeSpawn(result,exit);
    const got=await createTool(config,context(),fake.spawn).execute('id',{operation:'health'});
    assert.equal(got.details.status,'unavailable');
  }
});

test('extra child output blocks and incorrect error flags cannot escape',async()=>{
  const denied=synthetic('denied');
  for (const malformed of [{...denied,isError:false},
      {...denied,content:[...denied.content,{type:'text',text:'PRIVATE EXTRA'}]},
      {...denied,private_extra:'PRIVATE EXTRA'}]) {
    const fake=fakeSpawn(malformed,3);
    const result=await createTool(config,context(),fake.spawn).execute('id',{operation:'health'});
    assert.equal(result.details.status,'unavailable');
    assert.equal(JSON.stringify(result).includes('PRIVATE EXTRA'),false);
  }
});

test('revoked invocation never returns completed evidence',async()=>{
  let checks=0;
  const ctx={assertInvocationCurrent(){if (++checks===3) throw new Error('REVOKED PRIVATE');}};
  const fake=fakeSpawn();
  const result=await createTool(config,ctx,fake.spawn).execute('id',{operation:'health'});
  assert.equal(result.details.status,'denied');
  assert.equal(JSON.stringify(result).includes('REVOKED PRIVATE'),false);
});

test('abort terminates child and awaits close',async()=>{
  const fake=fakeSpawn(null);
  const controller=new AbortController();
  const pending=createTool(config,context(),fake.spawn).execute('id',{operation:'health'},controller.signal);
  controller.abort();
  const result=await pending;
  assert.equal(result.details.status,'unavailable');
  assert.deepEqual(fake.calls[1],{signal:'SIGKILL'});
});

test('already-aborted invocation does not spawn',async()=>{
  const fake=fakeSpawn();
  const controller=new AbortController();controller.abort();
  const result=await createTool(config,context(),fake.spawn).execute('id',{},controller.signal);
  assert.equal(result.details.status,'unavailable');
  assert.equal(fake.calls.length,0);
});

test('output cap kills child but does not settle until close',async()=>{
  const fake=fakeSpawn(null);
  let killed=false,settled=false;
  const spawn=(...args)=>{
    const child=fake.spawn(...args);
    child.kill=()=>{killed=true;};
    return child;
  };
  const pending=createTool(config,context(),spawn).execute('id',{operation:'health'});
  pending.then(()=>{settled=true;});
  const child=fake.calls[0].child;
  child.stdout.emit('data',Buffer.alloc(4*1024*1024+1));
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(killed,true);
  assert.equal(settled,false);
  child.emit('close',null);
  assert.equal((await pending).details.status,'unavailable');
});

test('real isolated Python failure is sanitized and disabled remains default',async()=>{
  const tool=createTool({...config,tokenFile:'/missing/canary-token'},context());
  const result=await tool.execute('id',{operation:'health'});
  assert.equal(result.details.status,'unavailable');
  assert.equal(JSON.stringify(result).includes('/missing'),false);
  assert.equal((await createTool({},context()).execute('id',{})).details.status,'disabled');
});
