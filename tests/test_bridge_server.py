import asyncio
import json
import unittest
from unittest.mock import patch
from html.parser import HTMLParser

from aiohttp import ClientSession, WSServerHandshakeError, WSMsgType
from aiohttp.test_utils import TestServer

from bridge.server import create_app
from bridge.controller import Controller
from bridge.backends import SimulatorBackend
from tests.test_bridge_controller import FakeBackend


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend = FakeBackend()
        self.controller = Controller(self.backend)
        self.server = TestServer(create_app(self.controller, port=0, simulator=True), host='127.0.0.1')
        await self.server.start_server()
        self.origin = str(self.server.make_url('')).rstrip('/')
        self.session = ClientSession()
        self.sockets = []

    async def asyncTearDown(self):
        for socket in self.sockets:
            await socket.close()
        await self.session.close()
        await self.server.close()

    async def bootstrap(self):
        async with self.session.get(self.server.make_url('/api/bootstrap')) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertNotIn('Access-Control-Allow-Origin', response.headers)
            return await response.json()

    async def socket(self):
        bootstrap = await self.bootstrap()
        ws = await self.session.ws_connect(self.server.make_url('/api/ws'), origin=self.origin)
        self.sockets.append(ws)
        await ws.send_json(dict(v=1, op='authorize', token=bootstrap['token']))
        self.assertEqual((await ws.receive_json())['event'], 'authorized')
        return ws

    async def request(self, ws, op, args=None, generation=0, request_id='a'):
        await ws.send_json(dict(v=1, op=op, args=args or {}, generation=generation, id=request_id))
        while True:
            msg = await asyncio.wait_for(ws.receive_json(), 1)
            if msg.get('id') == request_id:
                return msg

    async def test_foreign_host_and_fetch_site_rejected(self):
        for headers in ({'Host': 'evil.example'}, {'Sec-Fetch-Site': 'cross-site'}):
            async with self.session.get(self.server.make_url('/api/bootstrap'), headers=headers) as response:
                self.assertEqual(response.status, 403)
        self.assertEqual(self.backend.writes, [])

    async def test_foreign_origin_never_dispatches(self):
        for origin in ('https://example.org', 'null', None):
            with self.assertRaises(WSServerHandshakeError) as exc:
                await self.session.ws_connect(self.server.make_url('/api/ws'), origin=origin)
            self.assertEqual(exc.exception.status, 403)
        self.assertEqual(self.backend.writes, [])

    async def test_bad_token_never_dispatches(self):
        ws = await self.session.ws_connect(self.server.make_url('/api/ws'), origin=self.origin)
        await ws.send_json(dict(v=1, op='authorize', token='bad'))
        self.assertIn((await ws.receive()).type, (WSMsgType.CLOSE, WSMsgType.CLOSED))
        self.assertEqual(self.backend.writes, [])

    async def test_missing_authorization_times_out(self):
        with patch('bridge.server.AUTH_TIMEOUT', 0.02):
            ws = await self.session.ws_connect(self.server.make_url('/api/ws'), origin=self.origin)
            self.assertIn((await ws.receive()).type, (WSMsgType.CLOSE, WSMsgType.CLOSED))
        self.assertEqual(self.backend.writes, [])

    async def test_static_allowlist_excludes_private_files(self):
        for path in ('/.git/config', '/.venv/pyvenv.cfg', '/export.xml', '/README.md', '/%2e%2e/README.md'):
            async with self.session.get(self.server.make_url(path)) as response:
                self.assertEqual(response.status, 404)
        async with self.session.get(self.server.make_url('/')) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])

    async def test_strict_schema_and_message_limit(self):
        ws = await self.socket()
        for payload in (
            dict(v=1, id='bad', op='start', generation=0, args={}, extra='x'),
            dict(v=1, id='bad', op='raw_write', generation=0, args={}),
            dict(v=1, id='x'*65, op='discover', generation=0, args={}),
            dict(v=1, id='bad', op='connect', generation=0, args={'device_id':'x','uuid':'arbitrary'}),
        ):
            await ws.send_json(payload)
            result = await ws.receive_json()
            self.assertFalse(result['ok'])
        await ws.send_str('{"v":1,"v":1}')
        self.assertFalse((await ws.receive_json())['ok'])
        await ws.send_str('x' * 17000)
        self.assertIn((await ws.receive()).type, (WSMsgType.CLOSE, WSMsgType.CLOSED))
        self.assertEqual(self.backend.writes, [])

    async def test_discovery_does_not_connect_and_unknown_device_rejected(self):
        ws = await self.socket()
        result = await self.request(ws, 'discover')
        self.assertEqual(result['result']['devices'][0]['id'], 'synthetic')
        self.assertFalse(self.controller.connected)
        result = await self.request(ws, 'connect', {'device_id':'arbitrary'}, request_id='b')
        self.assertFalse(result['ok'])

    async def test_all_dashboard_assets_load_without_external_or_inline_dependencies(self):
        class Assets(HTMLParser):
            urls = []
            def handle_starttag(self, tag, attributes):
                attrs = dict(attributes)
                self_test.assertNotIn('style', attrs)
                if tag in ('script', 'link'):
                    self.urls.append(attrs.get('src') or attrs.get('href'))
        self_test = self
        async with self.session.get(self.server.make_url('/')) as response:
            html = await response.text()
        parser = Assets(); parser.feed(html)
        self.assertNotIn('<style', html)
        for asset in parser.urls:
            self.assertNotIn('://', asset)
            async with self.session.get(self.server.make_url('/' + asset)) as response:
                self.assertEqual(response.status, 200, asset)
        self.assertEqual(self.backend.writes, [])

    async def test_discovery_is_bounded(self):
        async def many(timeout):
            self.assertEqual(timeout, 5)
            return [dict(id=str(i), name='Synthetic') for i in range(100)]
        self.backend.discover = many
        ws = await self.socket()
        result = await self.request(ws, 'discover')
        self.assertEqual(len(result['result']['devices']), 32)

    async def test_burst_consumer_overflow_stops_independently(self):
        await self.server.close()
        self.controller = Controller(SimulatorBackend())
        self.server = TestServer(create_app(self.controller, port=0, simulator=True), host='127.0.0.1')
        await self.server.start_server()
        self.origin = str(self.server.make_url('')).rstrip('/')
        ws = await self.socket()
        await self.request(ws, 'discover')
        connected = await self.request(ws, 'connect', {'device_id':'simulator-ba09'}, request_id='c')
        await asyncio.sleep(0.01)
        await self.request(ws, 'start', generation=connected['result']['generation'], request_id='start')
        for _ in range(100): self.controller.emit('state', connected=True, blocked=False)
        await asyncio.sleep(0.05)
        self.assertEqual(self.controller.backend.state, 3)
        self.assertFalse(self.controller.connected)

    async def test_real_websocket_simulator_flow(self):
        # Full server/controller/backend flow, without a Bluetooth adapter.
        await self.server.close()
        self.controller = Controller(SimulatorBackend())
        self.server = TestServer(create_app(self.controller, port=0, simulator=True), host='127.0.0.1')
        await self.server.start_server()
        self.origin = str(self.server.make_url('')).rstrip('/')
        ws = await self.socket()
        devices = await self.request(ws, 'discover')
        connected = await self.request(ws, 'connect', {'device_id':devices['result']['devices'][0]['id']}, request_id='c')
        generation = connected['result']['generation']
        await asyncio.sleep(0.02)
        second = await self.socket()
        busy = await self.request(second, 'discover', request_id='busy')
        self.assertFalse(busy['ok'])
        result = await self.request(ws, 'start', generation=generation, request_id='s')
        self.assertTrue(result['ok'])
        observed = await asyncio.wait_for(second.receive_json(), 1)
        self.assertFalse(observed['snapshot']['is_owner'])
        denied = await self.request(second,'start',generation=generation,request_id='observer-start')
        self.assertFalse(denied['ok'])
        result = await self.request(ws, 'stop_disconnect', generation=generation, request_id='stop')
        self.assertTrue(result['result']['confirmed'])
        self.assertFalse(self.controller.connected)

class HistoryTests(unittest.IsolatedAsyncioTestCase):
    bootstrap = ServerTests.bootstrap
    async def asyncSetUp(self):
        import tempfile
        from pathlib import Path
        from bridge.store import WalkStore
        from bridge.recorder import Recorder
        self.temp=tempfile.TemporaryDirectory()
        await ServerTests.asyncSetUp(self)
        await self.server.close()
        self.store=WalkStore(Path(self.temp.name)/'state/walks.sqlite3')
        self.controller=Controller(self.backend,recorder=Recorder(self.store))
        self.server=TestServer(create_app(self.controller,port=0,simulator=True),host='127.0.0.1')
        await self.server.start_server()
        self.origin=str(self.server.make_url('')).rstrip('/')

    async def asyncTearDown(self):
        await ServerTests.asyncTearDown(self);self.temp.cleanup()

    async def test_token_history_import_conflict_and_restricted_post(self):
        from tests.test_bridge_store import walk
        boot=await self.bootstrap()
        self.assertEqual(boot['recording'],'bridge')
        self.assertTrue(boot['observers'])
        url=self.server.make_url('/api/walks')
        async with self.session.get(url) as response:self.assertEqual(response.status,403)
        headers={'X-PitPat-Token':boot['token'],'Origin':self.origin}
        async with self.session.post(self.server.make_url('/api/walks/import'),json={'walks':[walk()]},headers=headers) as response:
            self.assertEqual(response.status,200)
            self.assertEqual((await response.json())['imported'],1)
        async with self.session.get(url,headers=headers) as response:
            self.assertEqual((await response.json())['walks'],[walk()])
        conflict=walk();conflict['steps']=99
        async with self.session.post(self.server.make_url('/api/walks/import'),json={'walks':[walk('two'),conflict]},headers=headers) as response:
            self.assertEqual(response.status,409)
        self.assertEqual(len(self.store.page(50,None)['walks']),1)
        for path in ('/api/bootstrap','/api/ws','/index.html'):
            async with self.session.post(self.server.make_url(path),json={},headers=headers) as response:
                self.assertEqual(response.status,405)
        headers['Origin']='https://foreign.example'
        async with self.session.post(self.server.make_url('/api/walks/import'),json={'walks':[]},headers=headers) as response:
            self.assertEqual(response.status,403)
