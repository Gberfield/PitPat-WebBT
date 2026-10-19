"""Test-only safety child with an external, persistent synthetic GATT plant."""
import argparse,asyncio,json,signal
from pathlib import Path
from bridge.safety_core import SafetyCore
from bridge.safety_ipc import SafetyServer

class PlantBackend:
    def __init__(self,path):self.path=path;self.pending={};self.serial=0;self.reader_task=None;self.writer=None
    async def discover(self,timeout):return [{'id':'plant','name':'Synthetic persistent plant'}]
    async def connect(self,device_id,on_packet,on_lost):
        if device_id!='plant':raise ValueError('Unknown plant')
        self.reader,self.writer=await asyncio.open_unix_connection(str(self.path))
        async def read():
            try:
                while raw:=await self.reader.readline():
                    msg=json.loads(raw)
                    if 'packet' in msg:on_packet(bytes.fromhex(msg['packet']))
                    elif msg.get('id') in self.pending:self.pending[msg['id']].set_result(True)
            finally:on_lost()
        self.reader_task=asyncio.create_task(read())
    async def write(self,packet):
        self.serial+=1;key=str(self.serial);f=asyncio.get_running_loop().create_future();self.pending[key]=f
        try:
            self.writer.write((json.dumps({'id':key,'write':packet.hex()})+'\n').encode());await self.writer.drain();await f
        finally:self.pending.pop(key,None)
    async def disconnect(self):
        if self.writer:self.writer.close();await self.writer.wait_closed()
        if self.reader_task:self.reader_task.cancel();await asyncio.gather(self.reader_task,return_exceptions=True)

async def main():
    p=argparse.ArgumentParser();p.add_argument('--runtime-dir',type=Path,required=True);p.add_argument('--plant-socket',type=Path,required=True);args=p.parse_args()
    server=SafetyServer(SafetyCore(PlantBackend(args.plant_socket)),args.runtime_dir)
    end=asyncio.Event();loop=asyncio.get_running_loop()
    for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,end.set)
    try:await server.serve();await end.wait()
    finally:await server.close()
if __name__=='__main__':asyncio.run(main())
