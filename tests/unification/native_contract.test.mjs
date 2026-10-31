import test from 'node:test';
import assert from 'node:assert/strict';
import {enforceMinimumScore} from '../../unification/native_contract.mjs';

test('native lexical fallback cannot bypass neutral minimum score',()=>{
  const original={coverage:'partial',hits:[{score:0.2},{score:0.8},{score:0.5},{},{score:NaN}]};
  assert.deepEqual(enforceMinimumScore(original,0.5).hits,[{score:0.8},{score:0.5}]);
  assert.equal(original.hits.length,5);
  assert.equal(enforceMinimumScore(original,0.5).coverage,'partial');
  assert.equal(enforceMinimumScore(original,1.1).hits.length,0);
});

test('an omitted threshold does not manufacture a score',()=>{
  const page={hits:[{}]};assert.equal(enforceMinimumScore(page),page);
});

test('invalid thresholds fail explicitly',()=>{
  for(const threshold of [-1,NaN,Infinity,'0.5',null]){
    assert.throws(()=>enforceMinimumScore({hits:[]},threshold));
  }
});
