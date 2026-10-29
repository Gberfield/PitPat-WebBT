const {test}=require('node:test');const assert=require('node:assert/strict');const {execFileSync}=require('node:child_process');
test('Swift menu bar model fixture matches Model.js',()=>{
    assert.doesNotThrow(()=>execFileSync(process.execPath,[require.resolve('./gen-model-cases.cjs'),'--check'],{stdio:'pipe'}));
});
