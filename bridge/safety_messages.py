"""Strict private safety protocol. Browser tokens never cross this boundary."""
from dataclasses import dataclass,asdict
from typing import TypedDict
from .protocol import encode_command

MAX_FRAME=16384
MAX_PENDING=8
@dataclass(frozen=True)
class Authority:
    safety_id:str
    link_epoch:int
    fault_generation:int
    bridge_id:str
    grant_id:str|None
    command_seq:int
    def json(self):return asdict(self)
class SafetySnapshot(TypedDict,total=False):
    safety_id:str
    link_epoch:int
    fault_generation:int
    fault_id:str|None
    grant_id:str|None

ARGS={'observe':set(),'evidence':{'after_seq','limit'},'discover':set(),
      'connect':{'device_id'},'acquire':{'owner_id','owner_kind'},'renew':{'renewal_seq'},
      'release':set(),'owner_lost':set(),'start':{'speed'},'pause':{'speed'},'set_speed':{'speed'},
      'stop':set(),'stop_disconnect':set(),'recording_ready':{'ready','revision','fault_id'},
      'recover':{'fault_id','stop_confirmation_id','owner_id','owner_kind'}}
def identifier(value):return isinstance(value,str) and 1<=len(value)<=64

def validate_frame(frame,role):
    if (not isinstance(frame,dict) or set(frame)!={'v','id','op','authority','args'}
        or type(frame['v']) is not int or frame['v']!=1 or not identifier(frame['id'])
        or not isinstance(frame['op'],str) or frame['op'] not in ARGS
        or not isinstance(frame['args'],dict)):raise ValueError('Invalid safety frame')
    op=frame['op'];args=frame['args'];a=frame['authority']
    if set(args)!=ARGS[op]:raise ValueError('Invalid safety arguments')
    if role=='helper':
        if op not in ('observe','evidence','stop') or a is not None:raise ValueError('Helper may observe or Stop only')
    elif role=='application':
        if not isinstance(a,dict) or set(a)!=set(Authority.__dataclass_fields__):raise ValueError('Authority required')
        for k in ('safety_id','bridge_id'):
            if not identifier(a[k]):raise ValueError('Invalid incarnation')
        if a['grant_id'] is not None and not identifier(a['grant_id']):raise ValueError('Invalid grant')
        for k in ('link_epoch','fault_generation','command_seq'):
            if type(a[k]) is not int or a[k]<0:raise ValueError('Invalid authority counter')
    else:raise ValueError('Invalid role')
    if op in ('start','pause','set_speed'):encode_command(op,args['speed'])
    if op in ('acquire','recover'):
        if not identifier(args['owner_id']) or args['owner_kind'] not in ('tray','browser'):raise ValueError('Invalid owner')
    if op=='connect' and (not isinstance(args['device_id'],str) or not 1<=len(args['device_id'])<=128):raise ValueError('Invalid device')
    for k in ('renewal_seq','revision','after_seq','limit'):
        if k in args and (type(args[k]) is not int or args[k]<0):raise ValueError('Invalid counter')
    if op=='evidence' and not 1<=args['limit']<=256:raise ValueError('Invalid limit')
    if op=='recording_ready' and type(args['ready']) is not bool:raise ValueError('Invalid readiness')
    for k in ('fault_id','stop_confirmation_id'):
        if k in args and args[k] is not None and not identifier(args[k]):raise ValueError('Invalid confirmation identity')
    return frame
