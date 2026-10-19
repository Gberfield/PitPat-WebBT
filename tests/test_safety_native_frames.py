"""Full safety provenance must not overflow live tray messages."""
import asyncio,json,tempfile,unittest
from pathlib import Path
from bridge.backends import SimulatorBackend
from bridge.controller import Controller
from bridge.native import NativeServer
from bridge.protocol import parse_telemetry
from bridge.recorder import Recorder
from bridge.safety_client import SafetyClient
from bridge.safety_core import SafetyCore
from bridge.safety_ipc import SafetyServer
from bridge.store import WalkStore
from tests.test_bridge_controller import report

class FrameTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_evidence_stays_in_storage_without_overflowing_tray_events(self):
        # Regression: copying the bounded 256-packet evidence ring into both
        # walk-event data and snapshot makes a valid live frame exceed 64 KiB.
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);store=WalkStore(root/'state/walks.sqlite3')
            recorder=Recorder(store);await recorder.observe(parse_telemetry(report(1000,1)))
            fixtures=json.loads((Path(__file__).parent/'fixtures/protocol.json').read_text())
            packet=next(item['hex'] for item in fixtures if len(bytes.fromhex(item['hex']))==53)
            samples=[dict(seq=i,at=1000+i,hex=packet) for i in range(256)]
            await recorder.safety_evidence(dict(fault_id='synthetic-fault'),samples)
            safety=SafetyServer(SafetyCore(SimulatorBackend()),root/'safety')
            await safety.serve()
            facade=Controller(SafetyClient(safety.runtime,'app'),recorder=recorder)
            native=NativeServer(facade,root/'native');writer=None
            try:
                await facade.initialize();await native.serve()
                reader,writer=await asyncio.open_unix_connection(str(native.path),limit=256*1024)
                writer.write(b'{"v":1,"op":"hello","kind":"tray"}\n');await writer.drain()
                hello=await asyncio.wait_for(reader.readline(),1)
                facade.recorded(recorder.snapshot())
                update=await asyncio.wait_for(reader.readline(),1)
                self.assertEqual(json.loads(update)['event'],'walk')
                for frame in (hello,update):
                    self.assertLess(len(frame),65536,'Live tray frame includes bulk safety provenance')
                    session=json.loads(frame)['snapshot']['session']
                    self.assertEqual(session['status'],'interrupted')
                    self.assertEqual(session['sessionId'],recorder.snapshot()['sessionId'])
                self.assertEqual(store.current()['safetyEvidence']['samples'],samples)
            finally:
                if writer:writer.close();await writer.wait_closed()
                await native.close();await facade.shutdown();await safety.close()
