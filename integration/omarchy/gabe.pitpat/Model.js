// Plain JavaScript shared by QML and Node verification.
function targetUnits(mph) {
    if (!Number.isFinite(Number(mph))) throw Error('Invalid speed');
    return Math.min(6000,Math.max(1000,Math.round(Number(mph)*1.609344*10)*100));
}
function duration(seconds) {
    var n=Math.floor(seconds), h=Math.floor(n/3600),m=Math.floor(n%3600/60),s=n%60;
    return (h?h+'h ':'')+(m||h?m+'m ':'')+s+'s';
}
function view(snapshot,isOwner) {
    var s=snapshot||{}, m=s.metrics||{}, known=s.connected&&!s.stale&&m.state!==undefined;
    var healthy=known&&!s.blocked&&!s.recovery&&!s.storage_fault&&!s.stopping&&s.session?.status!=='interrupted';
    var state=s.stopping?'Stopping':s.connecting?'Connecting':!s.available?'Service unavailable':!s.connected?'Disconnected':
        !known||s.recovery?'Motion unknown':['Starting','Walking','Paused','Stopped'][m.state]||'Motion unknown';
    return {state:state,label:(s.simulator?'SIMULATOR · ':'')+state,
        owner:isOwner?'Tray controls motion':s.owner_kind?s.owner_kind+' controls motion · observing':'No motion controller',
        canStartPause:!!(isOwner&&healthy&&m.state!==0),canAdjust:!!(isOwner&&healthy&&m.state!==0),
        canStop:!!s.connected,canTakeControl:!!(!isOwner&&healthy&&s.owner_present&&m.state===3&&m.speed_raw===0),
        startText:m.state===1?'Pause':'Start',
        speed:known?(m.speed_raw/1000/(m.unit_mode?1:1.609344)).toFixed(2)+' mph':'—',
        distance:known?(m.distance/1000/(m.unit_mode?1:1.609344)).toFixed(3)+' mi':'—',
        calories:known?m.calories+' Cal':'—',steps:known?String(m.steps):'—',duration:known?duration(m.duration/1000):'—',
        target:((s.target_speed||1000)/1000/1.609344).toFixed(2)};
}
if(typeof module!=='undefined') module.exports={view:view,targetUnits:targetUnits};
