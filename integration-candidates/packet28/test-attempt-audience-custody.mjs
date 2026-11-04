import test from 'node:test';
import assert from 'node:assert/strict';
import { withAttemptAudienceCustody } from './attempt-audience-custody.ts';

for (const fault of ['none', 'create', 'prepare', 'backend', 'close', 'release', 'clear']) {
  test(`actual candidate helper: ${fault}`, async () => {
    const events = [];
    const step = name => { events.push(name); if (fault === name) throw new Error(name); };
    const run = withAttemptAudienceCustody(
      () => step('release'), () => step('clear'), async own => {
        step('create');
        own({ close: () => step('close') });
        step('prepare');
        await Promise.resolve();
        step('backend');
        return 42;
      });
    if (fault === 'none') assert.equal(await run, 42);
    else await assert.rejects(run, new RegExp(fault));
    assert.deepEqual(events.slice(-2), ['release', 'clear']);
    assert.equal(events.filter(e => e === 'release').length, 1);
    assert.equal(events.includes('close'), fault !== 'create');
  });
}

test('borrowed resolver no-op does not release the outer lease', async () => {
  let outerReleases = 0, clears = 0;
  const outerRelease = () => { outerReleases++; };
  await withAttemptAudienceCustody(() => {}, () => { clears++; }, async own => {
    own({ close() {} });
  });
  assert.equal(outerReleases, 0);
  assert.equal(clears, 1);
  outerRelease();
  assert.equal(outerReleases, 1);
});

test('cleanup waits for the operation promise; no premature release', async () => {
  let unblock, reached, releases = 0;
  const entered = new Promise(r => { reached = r; });
  const barrier = new Promise(r => { unblock = r; });
  const run = withAttemptAudienceCustody(() => { releases++; }, () => {}, async own => {
    own({ close() {} }); reached(); await barrier;
  });
  await entered;
  assert.equal(releases, 0);
  unblock(); await run;
  assert.equal(releases, 1);
});

test('nested faults cannot skip remaining cleanup; later error wins explicitly', async () => {
  const events = [];
  await assert.rejects(withAttemptAudienceCustody(
    () => { events.push('release'); throw new Error('release'); },
    () => { events.push('clear'); throw new Error('clear'); },
    async own => {
      own({ close() { events.push('close'); throw new Error('close'); } });
      throw new Error('backend');
    }), /clear/);
  assert.deepEqual(events, ['close', 'release', 'clear']);
});

test('duplicate registration rejects without losing the first controls', async () => {
  const events = [];
  await assert.rejects(withAttemptAudienceCustody(
    () => events.push('release'), () => events.push('clear'), async own => {
      own({ close: () => events.push('first-close') });
      own({ close: () => events.push('second-close') });
    }), /already registered/);
  assert.deepEqual(events, ['first-close', 'release', 'clear']);
});
