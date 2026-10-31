/** Private-local operator.read lease over a validated, entirely public projection.
 * Not a host-minted session capability. No production configuration or service control.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL, fileURLToPath} from 'node:url';
import {execFileSync, spawnSync} from 'node:child_process';
import {enforceMinimumScore} from './native_contract.mjs';

export const RUNTIME = '/Users/hanclaw/claw/openclaw';
export const REVISION = '4d94a9fac61f2e83331a09df18ad35cdfb1faf5c';
const CODE_ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const INVALID = 'generation invalid; rebuild required';
const MAX_REQUEST = 65536;

export function assertPin(revision) {
  if (revision !== REVISION) throw new Error('private-local runtime revision mismatch');
}
export function assertConfig(cfg, root, env = process.env) {
  const state = path.join(root, 'state');
  const expected = {OPENCLAW_STATE_DIR: state, OPENCLAW_CONFIG_PATH: path.join(root, 'openclaw.json')};
  if (Object.keys(env).some(k => k.startsWith('OPENCLAW_') && !(k in expected)) ||
      Object.entries(expected).some(([k,v]) => env[k] !== v)) throw new Error('explicit isolated state/config env required');
  const search = cfg.memory?.search;
  if (cfg.agents?.defaults?.workspace !== path.join(root,'workspace') ||
      cfg.agents?.entries?.pilot?.agentDir !== path.join(state,'agents/pilot/agent') ||
      (cfg.agents?.entries?.pilot?.workspace !== undefined && cfg.agents.entries.pilot.workspace !== path.join(root,'workspace')) ||
      !Array.isArray(search?.sources) || search.sources.length !== 1 || search.sources[0] !== 'memory' ||
      search.rememberAcrossConversations !== false || search.experimental?.sessionMemory !== false ||
      !Array.isArray(search.extraPaths) || search.extraPaths.length !== 0 || 'models' in cfg) {
    throw new Error('unsafe native partition configuration');
  }
  const url = new URL(search.remote?.baseUrl);
  if (search.provider !== 'openai-compatible' || search.fallback !== 'none' || url.protocol !== 'http:' ||
      !['127.0.0.1','[::1]'].includes(url.hostname) || url.username || url.password) {
    throw new Error('read-only loopback embedding transport required');
  }
}

// Kept injectable for hermetic tests. The CLI always uses the pinned real dependencies.
export async function openAdapter(root, registry, dependencies = {}) {
  if (await fs.realpath(root) !== path.resolve(root)) throw new Error('canonical isolated root required');
  root = path.resolve(root);
  assertPin((dependencies.readRevision || (() => execFileSync('git',['-C',RUNTIME,'rev-parse','HEAD'],{encoding:'utf8'}).trim()))());
  const cfg = JSON.parse(await fs.readFile(path.join(root,'openclaw.json'),'utf8'));
  assertConfig(cfg, root);
  const manifest = JSON.parse(await fs.readFile(path.join(root,'partition.json'),'utf8'));
  const validateGeneration = dependencies.validateGeneration || (() => {
    const result = spawnSync(process.argv[4] || 'python3', ['-m','unification.native_client','--validate',registry,root],
      {cwd:CODE_ROOT, input:JSON.stringify(manifest), encoding:'utf8',timeout:20000,maxBuffer:65536});
    if (result.error || result.status !== 0) throw new Error(INVALID);
  });
  await validateGeneration();
  // No other module in this implementation imports this private-local facade.
  const sdk = await (dependencies.loadFacade || (() => import(pathToFileURL(path.join(RUNTIME,'dist/plugin-sdk/memory-host-search.js')))))();
  let current = true;
  const context = {authority:{kind:'operator',scopes:['operator.read']},assertCurrent(){if (!current) throw new Error('lease revoked');}};
  let opened;
  try {
    opened = await sdk.getActiveMemoryProvider({cfg,agentId:'pilot',purpose:'cli',context});
    if (!opened.provider) throw new Error('native provider unavailable');
    return new NativeAdapter({provider:opened.provider, providerId:opened.providerId, cfg, root, manifest,
      validateGeneration, revoke:() => {current = false;}, closeManagers:() => sdk.closeActiveMemorySearchManagers(cfg)});
  } catch (error) {
    current = false;
    try {await opened?.provider?.close();} finally {await sdk.closeActiveMemorySearchManagers(cfg);}
    throw error;
  }
}

export class NativeAdapter {
  constructor({provider,providerId,cfg,root,manifest,validateGeneration,revoke,closeManagers}) {
    Object.assign(this,{provider,providerId,cfg,root,manifest,validateGeneration,revoke,closeManagers});
    this.records = new Map(manifest.records.map(r => [r.path,r]));
    this.closed = false;
  }
  envelope(status, results = [], fields = {}) {
    return {version:1,status,results,backends:[{id:'openclaw',status:['ok','empty'].includes(status)?'ready':status,
      ...(fields.reason ? {reason:fields.reason} : {})}],coverage:['ok','empty'].includes(status)?this.manifest.coverage:'partial',...fields};
  }
  evidence(record) {
    const e = record.evidence;
    return {...e,citation:{...e.citation,doc_id:e.doc_id},reference:{id:e.doc_id,revision:e.revision}};
  }
  async operation(req) {
    // Every call is bounded by a complete, freshly loaded registry validation.
    try {await this.validateGeneration();} catch {return this.envelope('unavailable',[],{reason:INVALID});}
    let result;
    try {
      if (req.verb === 'search') {
        const page = enforceMinimumScore(await this.provider.search({query:req.query,maxResults:req.maxResults ?? 8,
          minScore:req.minScore ?? 0,sources:['memory']}),req.minScore ?? 0);
        if (page.status && !['ok','empty'].includes(page.status)) throw new Error('native backend not ready');
        let dropped = 0;
        const hits = [];
        for (const hit of page.hits) {
          const record = this.records.get(hit.reference?.id);
          if (!record) {dropped++;continue;}
          hits.push({...this.evidence(record),score:hit.score,excerpt:hit.snippet ?? hit.excerpt ?? ''});
        }
        const results = hits.slice(0,req.maxResults ?? 8);
        result = this.envelope(results.length?'ok':'empty',results,{query:req.query,mode:'hybrid',dropped_outside_partition:dropped,
          coverage:page.coverage === 'partial' ? 'partial' : this.manifest.coverage});
      } else {
        const record = [...this.records.values()].find(r => r.evidence.doc_id === req.doc_id);
        if (!record) result = this.envelope('denied',[],{reason:'not authorized'});
        else if (req.revision != null && req.revision !== record.evidence.revision) result = this.envelope('stale',[],{reason:'source changed; search again'});
        else {
          const from = req.from ?? 1, lines = req.lines ?? 80;
          const got = await this.provider.get({reference:{providerId:this.providerId,id:record.path},from,lines});
          const source = await fs.readFile(path.join(this.root,'workspace',record.path),'utf8');
          const expected = source.split('\n').slice(from-1,from-1+lines).join('\n');
          const available = source.split(/\n/).length - (source.endsWith('\n')?1:0);
          const count = Math.max(0,Math.min(lines,available-from+1));
          if (got.status !== 'ok' || got.from !== from || !Number.isInteger(got.lines) || got.lines !== count ||
              typeof got.text !== 'string' || !got.text.startsWith(expected)) throw new Error('bounded native get failed');
          // Strip the native continuation notice; only validated source text leaves the boundary.
          result = this.envelope('ok',[],{...this.evidence(record),text:expected.slice(0,16000),start_line:from,
            source_line:record.evidence.source_start_line+from-1,lines_returned:count,
            truncated:expected.length>16000 || from-1+lines<available});
        }
      }
    } catch {result = this.envelope('unavailable',[],{reason:'native operation failed'});}
    try {await this.validateGeneration();} catch {return this.envelope('unavailable',[],{reason:INVALID});}
    return result;
  }
  async dispatch(req) {
    let id;
    try {
      if (!req || typeof req !== 'object' || Array.isArray(req) || !Number.isSafeInteger(req.id) || req.id < 1) throw new Error('positive request id required');
      id = req.id;
      if (!['hello','search','get','health','ping','shutdown'].includes(req.verb)) throw new Error('unsupported verb');
      if (req.verb === 'search' && (typeof req.query !== 'string' || !req.query.trim() || [...req.query].length>4000 ||
          !Number.isInteger(req.maxResults ?? 8) || (req.maxResults ?? 8)<1 || (req.maxResults ?? 8)>30 ||
          typeof (req.minScore ?? 0) !== 'number' || !Number.isFinite(req.minScore ?? 0) || (req.minScore ?? 0)<0)) throw new Error('invalid search budget');
      if (req.verb === 'get' && (typeof req.doc_id !== 'string' || req.doc_id.length>4000 ||
          !Number.isInteger(req.from ?? 1) || (req.from ?? 1)<1 || !Number.isInteger(req.lines ?? 80) || (req.lines ?? 80)<1 || (req.lines ?? 80)>200)) throw new Error('invalid read bounds');
      if (req.verb === 'shutdown') {await this.close();return {id,ok:true,status:'closed'};}
      if (this.closed) return {id,ok:true,...this.envelope('unavailable',[],{reason:'lease closed'})};
      if (['search','get'].includes(req.verb)) return {id,ok:true,...await this.operation(req)};
      if (req.verb === 'health') {
        const health = await this.provider.health();
        return {id,ok:true,...this.envelope(health.status === 'ready'?'ok':'unavailable'),health};
      }
      return {id,ok:true,status:'ok',version:1,revision:REVISION,coverage:this.manifest.coverage};
    } catch {return {id:id ?? null,ok:false,error:'invalid request or native backend unavailable'};}
  }
  async close() {
    if (this.closed) return;
    this.closed = true;
    this.revoke();
    try {await this.provider.close();} finally {await this.closeManagers();}
  }
}

export async function serve(adapter, input = process.stdin, output = process.stdout) {
  let pending = Buffer.alloc(0), oversized = false;
  const send = response => output.write(JSON.stringify(response)+'\n');
  try {
    for await (const chunk of input) {
      let rest = Buffer.from(chunk);
      while (rest.length) {
        const end = rest.indexOf(10), piece = end<0?rest:rest.subarray(0,end);
        if (!oversized) {
          if (pending.length+piece.length>MAX_REQUEST) {oversized=true;pending=Buffer.alloc(0);}
          else pending=Buffer.concat([pending,piece]);
        }
        if (end<0) break;
        rest=rest.subarray(end+1);
        if (oversized) send({id:null,ok:false,error:'request too large'});
        else {
          let req;
          try {req=JSON.parse(pending.toString('utf8'));} catch {send({id:null,ok:false,error:'invalid JSON'});pending=Buffer.alloc(0);continue;}
          send(await adapter.dispatch(req));
          if (req?.verb === 'shutdown' && adapter.closed) return;
        }
        pending=Buffer.alloc(0);oversized=false;
      }
    }
    if (pending.length || oversized) send({id:null,ok:false,error:'unterminated request'});
  } finally {await adapter.close();}
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  // Native diagnostics must never contaminate the line-delimited response stream.
  console.log = console.info = console.warn = (...args) => console.error(...args);
  let adapter;
  try {
    if (!process.argv[2] || !process.argv[3]) throw new Error('partition and registry required');
    adapter = await openAdapter(process.argv[2],process.argv[3]);
    for (const signal of ['SIGTERM','SIGINT']) process.once(signal,() => {
      adapter.close().finally(() => process.exit(0));
    });
    await serve(adapter);
  } catch {
    process.stderr.write('native adapter startup failed (pin, isolation, configuration or backend gate)\n');
    process.exitCode=1;
  } finally {await adapter?.close();}
}
