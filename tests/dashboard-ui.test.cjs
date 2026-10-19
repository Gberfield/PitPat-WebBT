const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createUI} = require('../dashboard-ui.js');
function document() {
    const nodes = new Map();
    function node(id) {
        if (!nodes.has(id)) nodes.set(id, {id, hidden:false, children:[], listeners:{},
            classList:{toggle(){}}, setAttribute(k,v){this[k]=v;},
            addEventListener(k,v){this.listeners[k]=v;}, appendChild(c){this.children.push(c);},
            replaceChildren(){this.children=[];}, showModal(){this.open=true;}, close(){this.open=false;}, focus(){this.focused=true;}});
        return nodes.get(id);
    }
    let serial=0;
    return {getElementById:node, createElement:()=>node('created'+serial++), querySelectorAll:()=>[], node};
}
test('cancelled picker never selects a device and device names remain text', async () => {
    const doc=document(), ui=createUI(doc, {hash:''});
    const choice=ui.chooseDevice([{id:'one',name:'<script>bad</script>'}]);
    assert.equal(doc.node('deviceChoices').children[0].textContent, '<script>bad</script>');
    doc.node('cancelDeviceBtn').listeners.click();
    assert.equal(await choice,null);
    const next=ui.chooseDevice([{id:'two',name:'Synthetic device'}]);
    doc.node('deviceChoices').children[0].listeners.click();
    assert.equal(await next,'two');
});
test('empty picker resolves without connecting', async () => {
    const doc=document();
    assert.equal(await createUI(doc,{hash:''}).chooseDevice([]),null);
});
test('tabs preserve focus and keyboard navigation without native anchor scrolling', () => {
    const doc=document(), tabs=[doc.node('controlsTab'),doc.node('historyTab')];
    for (let i=0;i<2;i++) {
        tabs[i].href=i===0?'#controls-panel':'#history-panel';
        tabs[i].getAttribute = key => tabs[i][key];
    }
    doc.querySelectorAll=()=>tabs;
    const urls=[];
    const ui=createUI(doc,{hash:''},{replaceState(_state,_title,url){urls.push(url);}});
    ui.init();
    let prevented=false;
    tabs[1].listeners.click({preventDefault(){prevented=true;}});
    assert.equal(prevented,true);
    assert.equal(doc.node('history-panel').hidden,false);
    tabs[1].listeners.keydown({key:'ArrowLeft',preventDefault(){}});
    assert.equal(doc.node('controls-panel').hidden,false);
    assert.equal(tabs[0].focused,true);
    assert.deepEqual(urls,['#history-panel','#controls-panel']);
});
