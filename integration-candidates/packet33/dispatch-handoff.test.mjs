// Execute the complete pinned dispatch module, with closed synthetic imports.
// No host dependency/provider/session module is imported or evaluated.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';

const root = process.env.PACKET33_HOST_SOURCE;
assert.ok(root, 'Explicit isolated source root required');
const relative = 'src/agents/embedded-agent-runner/run/';
const source = stripTypeScriptTypes(readFileSync(path.join(root, relative, 'run-attempt-dispatch.ts'), 'utf8'));
const binderRaw = readFileSync(path.join(root, relative, 'attempt-memory-binding.ts'), 'utf8');
const mutant = process.env.PACKET33_MUTANT;
const binderPolicy = process.env.PACKET33_DISABLED ? binderRaw : binderRaw.replace('const ATTEMPT_MEMORY_BINDING_ENABLED = false;', 'const ATTEMPT_MEMORY_BINDING_ENABLED = true;');
assert.equal((binderRaw.match(/const ATTEMPT_MEMORY_BINDING_ENABLED = false;/g) ?? []).length, 1);
let binderText = binderPolicy;
if (mutant === 'cross-pair') binderText = binderText.replace('record.admitted !== admitted || record.audience !== audience', 'false');
if (mutant === 'retain-binding') binderText = binderText.replaceAll('bindings.delete(binding);', '/* deliberately omitted */');
const binder = stripTypeScriptTypes(binderText);
const executorRaw = readFileSync(path.join(root, 'src/plugins/memory-invocation-executor.ts'), 'utf8');
assert.equal((executorRaw.match(/const INVOCATION_MEMORY_EXECUTOR_ENABLED = false;/g) ?? []).length, 1);
let executorText = process.env.PACKET33_DISABLED ? executorRaw : executorRaw.replace('const INVOCATION_MEMORY_EXECUTOR_ENABLED = false;', 'const INVOCATION_MEMORY_EXECUTOR_ENABLED = true;');
if (mutant === 'skip-binding') executorText = executorText.replace('assertAttemptMemoryBinding(binding, admittedRunContext, audience, callerContext, attemptSignal);', '/* deliberately omitted */');
const executor = stripTypeScriptTypes(executorText);
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
  const otherAudience = Object.freeze({ synthetic: 'other' });
  const otherAdmitted = Object.freeze({ synthetic: 'other-admitted' });
  let active = true;
  let liveBinding;
  let binderModule;
  let executorModule;
  let liveCaller;
  let liveSignal;
  let liveExecutor;
  let abortAttempt;
  const poisonRequest = new Proxy({}, { get() { throw new Error("request inspected"); }, ownKeys() { throw new Error("request enumerated"); } });
  const checkPair = () => {
    if (process.env.PACKET33_DISABLED) { assert.equal(liveBinding, undefined); return; }
    assert.ok(liveBinding);
    assert.equal(liveSignal, abortAttempt.signal);
    binderModule.namespace.assertAttemptMemoryBinding(liveBinding, admittedContext, audience, liveCaller, liveSignal);
    assert.equal(executorModule.namespace.dispatchInvocationRead(liveExecutor, poisonRequest).status, 'unavailable');
    const create = capture => executorModule.namespace.createInvocationMemoryExecutor({optIn: true, capture});
    const good = {binding: liveBinding, admittedRunContext: admittedContext, callerContext: liveCaller, signal: liveSignal};
    const crossedCaller = {authority: liveCaller.authority, assertCurrent: liveCaller.assertCurrent, signal: liveSignal};
    for (const crossed of [
      {...good, admittedRunContext: otherAdmitted},
      {...good, callerContext: crossedCaller},
      {...good, binding: {...liveBinding}},
      {...good, signal: new AbortController().signal},
    ]) assert.equal(create(() => crossed).status, 'unavailable', 'crossed capture refused');
    assert.throws(() => binderModule.namespace.assertAttemptMemoryBinding(liveBinding, otherAdmitted, audience, liveCaller, liveSignal), /binding unavailable/);
    assert.throws(() => binderModule.namespace.assertAttemptMemoryBinding(liveBinding, admittedContext, otherAudience, liveCaller, liveSignal), /binding unavailable/);
    assert.throws(() => binderModule.namespace.assertAttemptMemoryBinding({...liveBinding}, admittedContext, audience, liveCaller, liveSignal), /binding unavailable/);
  };
  const checkInvalid = () => {
    if (liveExecutor) assert.equal(executorModule.namespace.dispatchInvocationRead(liveExecutor, poisonRequest).status, 'denied', 'expired executor refused');
    if (liveBinding) assert.throws(() => binderModule.namespace.assertAttemptMemoryBinding(liveBinding, admittedContext, audience, liveCaller, liveSignal), /binding unavailable/);
  };
  const admittedContext = Object.freeze({ synthetic: 'admitted-context' });
  const controls = {
    close: () => { checkInvalid(); hit('close'); }, isCurrent: () => true,
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
    resolveAdmittedRunActiveAssertion: (context, signal) => {
      assert.ok(context === admittedContext || context === otherAdmitted);
      return () => { signal?.throwIfAborted(); if (!active) throw new Error('revoked'); };
    },
    recordAdmittedModelRoutingDecision: () => {},
    agentHarnessBuildsOpenClawTools: () => false,
    CODEX_HARNESS_ID: 'codex-not-used',
    prepareExecApprovalContinuationForAttempt: value => value,
    prepareAttemptSystemPromptAdditions: async () => ({}),
    resolveSessionSkillResourceSnapshot: () => undefined,
    resolveEmbeddedAttemptMemoryAudience: async () => {
      hit('acquire');
      return { memoryAudience: audience, release: () => { checkInvalid(); hit(borrowed ? 'borrowed-noop' : 'release'); } };
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
      assert.equal(substitutions.resolveAdmittedRunActiveAssertion(otherAdmitted)(), undefined);
      checkPair();
      if (fault === 'signal-abort') {
        abortAttempt.abort();
        assert.equal(executorModule.namespace.dispatchInvocationRead(liveExecutor, poisonRequest).status, 'denied');
        checkInvalid();
      }
      if (fault === 'revoke') {
        active = false;
        assert.throws(() => binderModule.namespace.assertAttemptMemoryBinding(liveBinding, admittedContext, audience, liveCaller, liveSignal), /revoked/);
        checkInvalid();
      }
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
  const link = specifier => {
    if (specifier === './attempt-memory-binding.js') {
      if (!binderModule) binderModule = new vm.SourceTextModule(binder, { context });
      return binderModule;
    }
    if (specifier === './attempt-audience-custody.js') return new vm.SourceTextModule(helper, { context });
    if (specifier === '../../../plugins/memory-invocation-executor.js') {
      if (!executorModule) executorModule = new vm.SourceTextModule(executor, {context});
      return executorModule;
    }
    if (specifier === '../agents/embedded-agent-runner/run/attempt-memory-binding.js') return binderModule;
    const binderImports = {
      '../agents/admitted-run-context.js': ['resolveAdmittedRunActiveAssertion'],
      './memory-audience.js': ['isHostMemoryAudience', 'assertMemoryCallerCurrent'],
      '../../admitted-run-context.js': ['resolveAdmittedRunActiveAssertion'],
      '../../../plugins/memory-audience.js': ['isHostMemoryAudience', 'assertMemoryAudienceCurrent'],
    };
    const names = binderImports[specifier] ?? declarations.get(specifier);
    assert.ok(names, `Unexpected import: ${specifier}`);
    return new vm.SyntheticModule(names, function () {
      for (const name of names) {
        const key = name === 'default' ? (specifier === 'node:path' ? 'path' : specifier === 'node:fs/promises' ? 'fs' : specifier) : name;
        const extra = {
          isHostMemoryAudience: value => value === audience || value === otherAudience,
          assertMemoryCallerCurrent: caller => { caller.assertCurrent(); caller.signal?.throwIfAborted(); assert.ok(caller.authority.audience === audience || caller.authority.audience === otherAudience); },
          assertMemoryAudienceCurrent: value => { assert.ok(value === audience || value === otherAudience); if (!active) throw new Error('revoked'); },
        };
        this.setExport(name, substitutions[key] ?? extra[key] ?? (() => { throw new Error(`Unconfigured mock ${specifier}:${name}`); }));
      }
    }, { context });
  };
  await module.link(async (specifier, referencing) => {
    const result = link(specifier);
    // Capture the actual dispatch handoff, while running the real wrapper.
    if (specifier === '../../../plugins/memory-invocation-executor.js') {
      await result.link(link);
      await result.evaluate();
      return new vm.SyntheticModule(['createInvocationMemoryExecutor'], function () {
        this.setExport('createInvocationMemoryExecutor', params => {
          const created = result.namespace.createInvocationMemoryExecutor(params);
          if (!process.env.PACKET33_DISABLED) assert.equal(created.status, 'prepared');
          else assert.equal(created.reason, 'disabled');
          liveExecutor = created.executor;
          return created;
        });
      }, {context});
    }
    if (specifier === './attempt-memory-binding.js') {
      await result.link(link);
      await result.evaluate();
      return new vm.SyntheticModule(['withBoundAttemptAudienceCustody'], function () {
        this.setExport('withBoundAttemptAudienceCustody', (release, clear, admitted, resolvedAudience, signal, captureCaller, operation) => {
          assert.equal(admitted, admittedContext);
          assert.equal(resolvedAudience, audience);
          return result.namespace.withBoundAttemptAudienceCustody(release, clear, admitted, resolvedAudience, signal, captureCaller, (own, binding, caller) => {
            liveBinding = binding; liveCaller = caller; liveSignal = signal;
            return operation(own, binding, caller);
          });
        });
      }, { context });
    }
    return result;
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
    setPostCompactionAbortController: controller => { abortAttempt = controller; },
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
  // Observe deliberate mutant rejections even if they fail before pending.
  running.catch(() => {});
  // A finite microtask drain avoids timers, I/O or an unbounded polling test.
  for (let i = 0; i < 30 && !f.events.includes('pending'); i++) await Promise.resolve();
  assert.ok(f.events.includes('pending'));
  assert.equal(f.events.includes('close'), false);
  assert.equal(f.events.includes('release'), false);
  settle();
  await running;
  assert.deepEqual(f.events.slice(-4), ['settled', 'close', 'release', 'clear']);
});

if (!process.env.PACKET33_DISABLED) for (const fault of ['revoke', 'signal-abort']) test(`actual dispatch invalidates after ${fault}`, async () => {
  const f = await fixture(fault);
  await f.run();
  assert.deepEqual(f.events.slice(-3), ['close', 'release', 'clear']);
});

test('shipped disabled binder ignores captured pair and authority imports', async () => {
  const context = vm.createContext({});
  const module = new vm.SourceTextModule(stripTypeScriptTypes(binderRaw), { context });
  await module.link(specifier => {
    if (specifier === './attempt-audience-custody.js') return new vm.SourceTextModule(helper, { context });
    const names = specifier.includes('admitted-run-context') ? ['resolveAdmittedRunActiveAssertion'] : ['assertMemoryAudienceCurrent', 'isHostMemoryAudience'];
    return new vm.SyntheticModule(names, function () {
      for (const name of names) this.setExport(name, () => { throw new Error('disabled authority inspected'); });
    }, { context });
  });
  await module.evaluate();
  const poison = new Proxy({}, { get() { throw new Error('disabled pair inspected'); } });
  const events = [];
  const result = await module.namespace.withBoundAttemptAudienceCustody(
    () => events.push('release'), () => events.push('clear'), poison, poison, poison, () => { throw new Error("disabled caller inspected"); },
    async (own, binding) => { assert.equal(binding, undefined); own({close: () => events.push('close')}); return 'done'; },
  );
  assert.equal(result, 'done');
  assert.deepEqual(events, ['close', 'release', 'clear']);
});

 test('shipped disabled executor ignores every input property', async () => {
 const context = vm.createContext({}); const m = new vm.SourceTextModule(stripTypeScriptTypes(executorRaw), {context});
 await m.link(spec => { const names = spec.includes('attempt-memory-binding') ? ['assertAttemptMemoryBinding'] : spec.includes('admitted-run-context') ? ['resolveAdmittedRunActiveAssertion'] : ['assertMemoryCallerCurrent', 'isHostMemoryAudience']; return new vm.SyntheticModule(names, function() {for (const n of names) this.setExport(n, () => {throw new Error('disabled authority inspected');});}, {context}); });
 await m.evaluate(); const poison = new Proxy({}, {get() {throw new Error('disabled params inspected');}});
 assert.equal(m.namespace.createInvocationMemoryExecutor(poison).reason, 'disabled');
 });
