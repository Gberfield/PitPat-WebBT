"""Deadlines use elapsed boot time, including host suspension."""
import secrets
import time

CHALLENGE_INTERVAL=.25
HEALTH_TIMEOUT=2.0
TICK_INTERVAL=.05
OWNER_TIMEOUT=6.0
TELEMETRY_TIMEOUT=5.0

def boot_seconds():
    return time.clock_gettime(time.CLOCK_BOOTTIME)

class HealthMonitor:
    def __init__(self,clock=boot_seconds):
        self.clock=clock;self.bridge_id=None;self.last=None;self.sequence=0
        self.accepted_sequence=0;self.pending={};self.healthy=False
    def attach(self,bridge_id):
        if self.bridge_id is not None:raise ValueError('Application already attached')
        self.bridge_id=bridge_id;self.last=self.clock();self.pending={};self.healthy=False
    def detach(self):
        self.bridge_id=None;self.last=None;self.pending={};self.healthy=False
    def expired(self):
        return self.last is None or self.clock()-self.last>=HEALTH_TIMEOUT
    def issue_challenge(self):
        self.sequence+=1;now=self.clock()
        self.pending={k:v for k,v in self.pending.items() if now-v[1]<HEALTH_TIMEOUT}
        nonce=secrets.token_hex(16);self.pending[self.sequence]=(nonce,now)
        return dict(bridge_id=self.bridge_id,challenge_seq=self.sequence,nonce=nonce)
    def accept_health(self,frame):
        if self.expired() or frame.get('bridge_id')!=self.bridge_id:return False
        seq=frame.get('challenge_seq')
        if type(seq) is not int:return False
        item=self.pending.pop(seq,None)
        if (item is None or type(seq) is not int or seq<=self.accepted_sequence
            or frame.get('nonce')!=item[0] or self.clock()-item[1]>=HEALTH_TIMEOUT):return False
        self.accepted_sequence=seq;self.last=self.clock();self.healthy=True
        self.pending={k:v for k,v in self.pending.items() if k>seq}
        return True
