// Prepared optional tool plugin. Import/registration performs no token/network I/O.
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {dirname,isAbsolute,resolve} from 'node:path';
import parameters from './tool-parameters.json' with {type:'json'};

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const PYTHON = '/opt/homebrew/opt/python@3.14/bin/python3.14';
const BOOT = 'import sys;sys.path.insert(0,sys.argv[1]);from unification.canary_tool import main;raise SystemExit(main(sys.argv[2:]))';
export const NAME = 'cindylou_memory_canary';

function failure(status) {
  const details = {version:1,status,results:[],coverage:'partial',
    caller:{id:'isolated-public-tool-canary',audience:'public',domain:'campaign',production_integration:false}};
  return {content:[{type:'text',text:JSON.stringify(details)}],details,isError:true};
}

export function createTool(config, context, spawnChild=spawn, codeRoot=ROOT) {
  config={enabled:config.enabled,tokenFile:config.tokenFile,port:config.port};
  // A public-only tool never elevates on owner/sender/session-key identity.
  if (context.sandboxed || typeof context.assertInvocationCurrent !== 'function') return null;
  return {
    name:NAME,label:'Cindy memory canary',
    description:'Opt-in public campaign memory pilot. Only two reviewed sections; search candidates are not answers. Use returned revision for bounded get. No private notes, rules, capture or legacy fallback.',
    parameters,executionMode:'sequential',
    async execute(_toolCallId, request, signal) {
      try {context.assertInvocationCurrent();} catch {return failure('denied');}
      if (config.enabled !== true) return failure('disabled');
      if (signal?.aborted) return failure('unavailable');
      if (typeof codeRoot !== 'string' || !isAbsolute(codeRoot)) return failure('unavailable');
      if (typeof config.tokenFile !== 'string' || !config.tokenFile.startsWith('/') ||
          !Number.isInteger(config.port ?? 18091) || (config.port ?? 18091)<1024 || (config.port ?? 18091)>65535) return failure('unavailable');
      let raw;
      try {
        raw=JSON.stringify(request);
        if (typeof raw !== 'string' || Buffer.byteLength(raw)>8192) return failure('invalid_request');
      } catch {return failure('invalid_request');}
      const result = await new Promise(resolve => {
        let child, settled=false, stdout=[], size=0, failed=false, timer;
        const finish = result => {
          if (settled) return;
          settled=true; clearTimeout(timer);
          signal?.removeEventListener('abort',abort);
          resolve(result);
        };
        const stop = () => {failed=true;child?.kill('SIGKILL');};
        const abort = () => stop();
        try {
          context.assertInvocationCurrent();
          child=spawnChild(PYTHON,['-I','-c',BOOT,codeRoot,'--enable-canary',
            '--token-file',config.tokenFile,'--port',String(config.port ?? 18091),'--timeout','12'],
            {cwd:'/',stdio:['pipe','pipe','ignore'],env:{PATH:'/usr/bin:/bin'}});
          timer=setTimeout(stop,15000);
          signal?.addEventListener('abort',abort,{once:true});
          if (signal?.aborted) stop();
          child.on('error',()=>finish(failure('unavailable')));
          child.stdout.on('data',chunk=>{
            size+=chunk.length;
            if (size>4*1024*1024) {stop();return;}
            stdout.push(chunk);
          });
          child.on('close',code=>{
            if (failed) return finish(failure('unavailable'));
            try {
              const result=JSON.parse(Buffer.concat(stdout).toString('utf8'));
              const expected={disabled:2,invalid_request:2,denied:3,stale:4,unavailable:5,ok:0,empty:0};
              if (!result.details || !Object.hasOwn(expected,result.details.status) || code!==expected[result.details.status] ||
                  result.details.version!==1 || result.details.coverage!=='partial' || !Array.isArray(result.details.results) ||
                  result.details.caller?.audience!=='public' || result.details.caller?.domain!=='campaign' || result.details.caller?.production_integration!==false ||
                  !Array.isArray(result.content) || result.content.length!==1 || result.content[0]?.type!=='text' ||
                  Object.keys(result.content[0]).some(key=>!['type','text'].includes(key)) ||
                  Object.keys(result).some(key=>!['content','details','isError'].includes(key)) ||
                  result.isError!==!['ok','empty'].includes(result.details.status) ||
                  JSON.stringify(JSON.parse(result.content[0].text))!==JSON.stringify(result.details)) throw new Error();
              finish({content:[{type:'text',text:JSON.stringify(result.details)}],details:result.details,isError:result.isError});
            } catch {finish(failure('unavailable'));}
          });
          child.stdin.on('error',stop);
          child.stdin.end(raw);
        } catch {if (child) stop(); else finish(failure('unavailable'));}
      });
      try {context.assertInvocationCurrent();} catch {return failure('denied');}
      return signal?.aborted ? failure('unavailable') : result;
    },
  };
}

export default {
  id:'cindylou-memory-canary',name:'Cindy public memory canary',
  register(api) {
    // OpenClaw executes captured plugin modules from a different filesystem root.
    // Its host-selected original source, not import.meta.url/runtimeSource, owns
    // the adjacent pinned Python release. Missing host provenance fails closed.
    const codeRoot = typeof api.source === 'string' && isAbsolute(api.source)
      ? resolve(dirname(api.source),'../..') : null;
    api.registerTool({contextVersion:2,create(context) {
      return createTool({...api.pluginConfig},context,spawn,codeRoot);
    }},{name:NAME,optional:true});
  },
};
