#!/usr/bin/env node
/** PRIVATE-LOCAL capability experiment; no server, no production config/RPC.
 * Authority is operator.read over an entirely public, isolated partition ONLY.
 * This is NOT a host-minted session capability or a production adapter.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
import {performance} from 'node:perf_hooks';
import {enforceMinimumScore} from '../unification/native_contract.mjs';

const [runtimeRoot, partitionRoot, expectedRevision] = process.argv.slice(2);
if (!runtimeRoot || !partitionRoot || !expectedRevision) throw new Error('runtime, partition and pinned revision required');
const root = await fs.realpath(partitionRoot);
if (root !== path.resolve(partitionRoot)) throw new Error('canonical isolated root required');
const state = path.join(root,'state');
const configPath = path.join(root,'openclaw.json');
if (process.env.OPENCLAW_STATE_DIR !== state || process.env.OPENCLAW_CONFIG_PATH !== configPath) {
  throw new Error('explicit isolated state/config env required before imports');
}
const revision = execFileSync('git',['-C',runtimeRoot,'rev-parse','HEAD'],{encoding:'utf8'}).trim();
if (revision !== expectedRevision) throw new Error('private-local runtime revision mismatch');
const cfg = JSON.parse(await fs.readFile(configPath,'utf8'));
const manifest = JSON.parse(await fs.readFile(path.join(root,'partition.json'),'utf8'));
const workspace = path.join(root,'workspace');
if (cfg.agents?.defaults?.workspace !== workspace || cfg.agents?.entries?.pilot?.agentDir !== path.join(state,'agents/pilot/agent') ||
    cfg.memory?.search?.sources?.join(',') !== 'memory' || cfg.memory.search.rememberAcrossConversations !== false ||
    cfg.memory.search.experimental?.sessionMemory !== false || cfg.memory.search.extraPaths?.length) {
  throw new Error('unsafe native partition configuration');
}
const embeddingUrl = new URL(cfg.memory.search.remote?.baseUrl);
if (cfg.memory.search.provider !== 'openai-compatible' || embeddingUrl.protocol !== 'http:' || !['127.0.0.1','[::1]'].includes(embeddingUrl.hostname) || cfg.models || cfg.memory.search.fallback !== 'none') throw new Error('read-only loopback embedding transport required');
const report = {version:1, revision, authority:'local operator.read; public partition only',
  productionChanged:false, sourceCount:manifest.records.length, queries:[], checks:{}};
const sdk = await import(pathToFileURL(path.join(runtimeRoot,'dist/plugin-sdk/memory-host-search.js')));
let current = true;
const context = {authority:{kind:'operator',scopes:['operator.read']}, assertCurrent(){if(!current) throw new Error('experiment revoked');}};
let provider;
try {
  const opened = await sdk.getActiveMemoryProvider({cfg,agentId:'pilot',purpose:'cli',context});
  provider = opened.provider;
  if (!provider) throw new Error(opened.error || 'native provider unavailable');
  report.providerId = opened.providerId;
  report.adapter = opened.adapter;
  report.capabilities = provider.capabilities;
  // The installed legacy facade advertises both supported source kinds even
  // when only memory is configured. Capability is not corpus membership.
  report.checks.memoryOnlyConfigured = cfg.memory.search.sources.join(',') === 'memory';
  const start = performance.now();
  await provider.refresh();
  report.refreshMs = performance.now()-start;
  report.health = await provider.health();
  const legacyHealth = report.health.details?.legacy;
  if (report.health.status !== 'ready' || legacyHealth?.vector?.index?.state !== 'complete' || legacyHealth?.custom?.searchMode !== 'hybrid' || legacyHealth?.files !== manifest.records.length) throw new Error('native hybrid/index health proof failed');
  const allowed = new Set(manifest.records.map(r=>r.path));
  for (const query of ['Tom Erlichman','living guard released contact','diesel program Volunteer State']) {
    for (let run=0;run<3;run++) {
      const before = performance.now();
      const page = enforceMinimumScore(await provider.search({query,maxResults:5,minScore:0,sources:['memory']}),0);
      if (query === 'Tom Erlichman' && page.hits.length === 0) throw new Error('positive native entity query returned no evidence');
      for (const hit of page.hits) {
        if (!allowed.has(hit.reference.id)) throw new Error('native hit outside public partition');
        const got = await provider.get({reference:hit.reference,from:1,lines:2});
        report.lastGetProbe = {status:got.status,characters:got.text?.length,returnedLines:got.text?.split('\n').length,from:got.from,lines:got.lines};
        const input = await fs.readFile(path.join(workspace,hit.reference.id),'utf8');
        const expected = input.split('\n').slice(0,2).join('\n');
        // Native text appends a continuation notice outside its source-line count.
        if (got.status !== 'ok' || got.from !== 1 || got.lines > 2 || !got.text.startsWith(expected)) throw new Error('bounded native get failed');
      }
      report.queries.push({query,run,ms:performance.now()-before,page});
    }
  }
  const sessions = await provider.search({query:'Tom Erlichman',maxResults:5,minScore:0,sources:['sessions']});
  report.checks.sessionsEmpty = sessions.hits.length === 0;
  const high = await provider.search({query:'Tom Erlichman',minScore:1.1,maxResults:5,sources:['memory']});
  report.observations = {rawNativeHonorsMinScore:high.hits.length === 0,rawHighThresholdScores:high.hits.map(h=>h.score)};
  report.checks.adapterMinScore = enforceMinimumScore(high,1.1).hits.length === 0;
  const denied = [];
  for (const id of ['../MEMORY.md','/Users/hanclaw/.openclaw/workspace-cindylou/MEMORY.md','memory/unknown.md']) {
    try { const got = await provider.get({reference:{providerId:opened.providerId,id},from:1,lines:2}); denied.push(got.status === 'not_found'); }
    catch { denied.push(true); }
  }
  report.checks.outsideReadsDenied = denied.every(Boolean);
  current=false;
  try { await provider.search({query:'Tom'}); report.checks.revocation = false; }
  catch { report.checks.revocation = true; }
  if (Object.values(report.checks).some(ok=>!ok)) throw new Error('native boundary check failed');
} catch (error) {
  report.failure = {name:error.name,message:error.message};
  process.exitCode=1;
} finally {
  if (provider) {await provider.close();report.closed=true;}
  await sdk.closeActiveMemorySearchManagers(cfg);
  await fs.writeFile(path.join(root,'native-report.json'),JSON.stringify(report,null,2)+'\n',{mode:0o600});
}
console.log(JSON.stringify({report:path.join(root,'native-report.json'), checks:report.checks, failure:report.failure, queries:report.queries.length}));
