// Execute the complete pinned dispatch module, with closed synthetic imports.
// No host dependency/provider/session module is imported or evaluated.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';

const root = process.env.PACKET29_HOST_SOURCE;
assert.ok(root, 'Explicit isolated source root required');
const relative = 'src/agents/embedded-agent-runner/run/';
const source = stripTypeScriptTypes(readFileSync(path.join(root, relative, 'run-attempt-dispatch.ts'), 'utf8'));
const helper = stripTypeScriptTypes(readFileSync(path.join(root, relative, 'attempt-audience-custody.ts'), 'utf8'));

async function fixture(fault, borrowed = false, gate) {
  const events = [];
  const error = new Error(fault ?? 'unused');
  const abortError = new Error('post-compaction-abort');
  const hit = name => {
    events.push(name);
    if (fault === name || (fault === 'nested' && ['close', 'release', 'clear'].includes(name))) throw error;
  };
  const audience = Object.freeze({ synthetic: true });
  const admittedContext = Object.freeze({ synthetic: 'admitted-context' });
  const controls = {
    close: () => hit('close'), isCurrent: () => true,
    abortSignal: new AbortController().signal,
  };
  let forwarded;
  const substitutions = {
    fs: { mkdir: async () => hit('mkdir') }, path,
    attachModelProviderRuntimePluginHandle: model => model,
    resolveEmbeddedAttemptBasePrompt: () => 'synthetic prompt',
    resolveAttemptDispatchApiKey: () => undefined,
    buildAgentRuntimePlan: () => ({ synthetic: true }),
    mapThinkingLevelForProvider: () => 'medium',
    resolveAttemptTrajectoryAttribution: () => ({}),
    resolveAdmittedRunActiveAssertion: () => () => {},
    recordAdmittedModelRoutingDecision: () => {},
    agentHarnessBuildsOpenClawTools: () => false,
    CODEX_HARNESS_ID: 'codex-not-used',
    prepareExecApprovalContinuationForAttempt: value => value,
    prepareAttemptSystemPromptAdditions: async () => ({}),
    resolveSessionSkillResourceSnapshot: () => undefined,
    resolveEmbeddedAttemptMemoryAudience: async () => {
      hit('acquire');
      return { memoryAudience: audience, release: () => hit(borrowed ? 'borrowed-noop' : 'release') };
    },
    captureAgentPluginRuntimeRefresh: () => { hit('refresh'); return { isPending: false }; },
    resolveReplyExpectation: () => undefined,
    resolveHarnessWorkspace: () => ({}),
    remapSkillReferencePaths: prompt => { hit('params'); return prompt; },
    resolveDelegationCapability: () => undefined,
    createToolTerminalObserver: () => undefined,
    getGatewayContextResolver: context => {
      assert.equal(context, admittedContext);
      return 'synthetic-resolver';
    },
    createAgentHarnessCompletionScope: value => {
      assert.equal(value.gatewayContextResolver, 'synthetic-resolver');
      return { synthetic: true };
    },
    applyLocalNoAuthHeaderOverride: model => model,
    applyAuthHeaderOverride: model => model,
    MAX_BEFORE_AGENT_FINALIZE_REVISIONS: 1,
    withPreparedEmbeddedGatewayTools: (params, isCurrent, operation) => {
      hit('gateway');
      assert.equal(isCurrent, controls.isCurrent);
      forwarded = params;
      return Promise.resolve().then(operation);
    },
    runEmbeddedAttemptWithBackend: async params => {
      hit('backend');
      assert.equal(params.memoryAudience, audience);
      assert.equal(params.admittedRunContext, admittedContext);
      assert.equal(params.abortSignal, controls.abortSignal);
      if (gate) { hit('pending'); await gate; hit('settled'); }
      if (fault === 'reject' || fault === 'abort-substitute') throw error;
      return { syntheticResult: true };
    },
  };
  // Parse only the import declarations of this pinned source. Every unprovided
  // callable throws, so an unexpected dependency cannot silently become a no-op.
  const declarations = new Map();
  for (const match of source.matchAll(/import\s+([\s\S]*?)\s+from\s+["']([^"']+)["'];/g)) {
    const names = match[1].trim().startsWith('{')
      ? match[1].replace(/[{}]/g, '').split(',').map(s => s.trim().split(/\s+as\s+/)[0]).filter(Boolean)
      : ['default'];
    declarations.set(match[2], names);
  }
  const context = vm.createContext({ AbortController });
  const module = new vm.SourceTextModule(source, { context, identifier: 'pinned-dispatch' });
  await module.link(specifier => {
    if (specifier === './attempt-audience-custody.js') {
      return new vm.SourceTextModule(helper, { context, identifier: 'exact-candidate-helper' });
    }
    const names = declarations.get(specifier);
    assert.ok(names, `Unexpected import: ${specifier}`);
    return new vm.SyntheticModule(names, function () {
      for (const name of names) {
        const key = name === 'default' ? (specifier === 'node:path' ? 'path' : specifier === 'node:fs/promises' ? 'fs' : specifier) : name;
        this.setExport(name, substitutions[key] ?? (() => { throw new Error(`Unconfigured mock ${specifier}:${name}`); }));
      }
    }, { context });
  });
  await module.evaluate();
  const input = {
    provider: 'synthetic', modelId: 'synthetic', startupStagesEmitted: true,
    runInput: {
      runParams: { admittedRunContext: admittedContext, sessionKey: 'synthetic', config: {}, prompt: 'fake', disableTrajectory: true },
      workspaceResolution: { agentId: 'synthetic' }, workspaceDir: '/never-created',
      progressController: { resolveAttemptFastModeParam: () => false },
      laneController: { createAttemptControls: () => { hit('create'); return controls; } },
    },
    preparedRuntime: {
      snapshot: () => ({ effectiveModel: { api: 'fake' }, agentHarness: { id: 'fake' }, runtimeAuthState: null }),
      resolveRunAttemptAuthProfileStore: () => undefined,
    },
    sessionPromptState: { activePrompt: {}, settleOwnedTranscriptProjection: async () => {} },
    terminalRetryState: {}, bootstrapPromptWarningSignaturesSeen: [],
    resolveRuntimeFallbackReason: () => undefined,
    setPostCompactionAbortController: () => {},
    clearPostCompactionAbortController: () => hit('clear'),
    getPostCompactionAbortError: () => fault === 'abort-substitute' ? abortError : undefined,
  };
  return { events, error, abortError, run: () => module.namespace.prepareAndDispatchEmbeddedRunAttempt(input), getForwarded: () => forwarded };
}

for (const fault of [undefined, 'create', 'refresh', 'params', 'gateway', 'backend', 'reject', 'close', 'release', 'clear', 'nested', 'abort-substitute']) {
  test(`actual dispatch boundary: ${fault ?? 'success'}`, async () => {
    const f = await fixture(fault);
    if (fault) await assert.rejects(f.run, e => e === (fault === 'abort-substitute' ? f.abortError : f.error));
    else {
      const result = await f.run();
      assert.equal(result.dispatchedAttempt.preparedAttempt, f.getForwarded());
      assert.equal(result.dispatchedAttempt.rawAttempt.syntheticResult, true);
    }
    assert.equal(f.events.filter(x => x === 'release').length, 1);
    assert.equal(f.events.filter(x => x === 'clear').length, 1);
    assert.deepEqual(f.events.slice(-2), ['release', 'clear']);
    assert.equal(f.events.includes('close'), fault !== 'create');
    if (['create', 'refresh', 'params', 'gateway'].includes(fault)) assert.equal(f.events.includes('backend'), false);
  });
}

test('actual dispatch keeps borrowed release callback as a no-op', async () => {
  const f = await fixture(undefined, true);
  await f.run();
  assert.deepEqual(f.events.slice(-3), ['close', 'borrowed-noop', 'clear']);
  assert.equal(f.events.includes('release'), false);
});

test('actual dispatch does not release until backend promise settles', async () => {
  let settle;
  const gate = new Promise(resolve => { settle = resolve; });
  const f = await fixture(undefined, false, gate);
  const running = f.run();
  // A finite microtask drain avoids timers, I/O or an unbounded polling test.
  for (let i = 0; i < 30 && !f.events.includes('pending'); i++) await Promise.resolve();
  assert.ok(f.events.includes('pending'));
  assert.equal(f.events.includes('close'), false);
  assert.equal(f.events.includes('release'), false);
  settle();
  await running;
  assert.deepEqual(f.events.slice(-4), ['settled', 'close', 'release', 'clear']);
});
