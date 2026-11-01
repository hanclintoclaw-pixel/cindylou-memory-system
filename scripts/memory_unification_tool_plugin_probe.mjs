// Registration harness ONLY: no claim of real Gateway discovery/admission.
import plugin from '../integrations/openclaw-memory-canary/index.mjs';
import {fileURLToPath} from 'node:url';
let definition;
const [tokenFile,port,mode]=process.argv.slice(2);
plugin.register({source:fileURLToPath(new URL('../integrations/openclaw-memory-canary/index.mjs',import.meta.url)),
  pluginConfig:{enabled:mode==='enabled',tokenFile,port:Number(port)},
  registerTool(factory,options) {
    if (options.name!=='cindylou_memory_canary' || options.optional!==true || factory.contextVersion!==2) throw new Error('invalid registration');
    definition=factory;
  }});
let raw='';
for await (const chunk of process.stdin) {
  raw+=chunk.toString('utf8');
  if (Buffer.byteLength(raw)>8192) throw new Error('probe input too large');
}
const tool=definition.create({sandboxed:false,assertInvocationCurrent(){}});
const result=await tool.execute('isolated-probe',JSON.parse(raw));
console.log(JSON.stringify(result));
process.exitCode={disabled:2,invalid_request:2,denied:3,stale:4,unavailable:5}[result.details.status]??0;
