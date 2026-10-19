"""Restricted same-origin HTTP/WebSocket boundary. No public network binding."""
import asyncio
import contextlib
import json
import secrets
from pathlib import Path

from aiohttp import web, WSMsgType

ROOT = Path(__file__).resolve().parent.parent
ASSETS = {'/': 'index.html', **{f'/{name}': name for name in (
    'index.html', 'walks.js', 'protocol.js', 'transports.js', 'treadmill.js',
    'dashboard.css', 'dashboard-ui.js')}}
AUTH_TIMEOUT = 3
from .messages import load_json, validate_request


def create_app(controller, *, port=8765, simulator=False, native=None):
    token = secrets.token_urlsafe(32)
    sockets = set()

    @web.middleware
    async def restrict(request, handler):
        actual_port = port or request.transport.get_extra_info('sockname')[1]
        host = f'127.0.0.1:{actual_port}'
        if request.headers.get('Host') != host or request.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise web.HTTPForbidden()
        origin = request.headers.get('Origin')
        if origin is not None and origin != f'http://{host}':
            raise web.HTTPForbidden()
        if request.method != 'GET' and not (request.method == 'POST' and request.path == '/api/walks/import'):
            raise web.HTTPMethodNotAllowed(request.method, ['GET'])
        response = await handler(request)
        if not response.prepared:
            response.headers.update({
                'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                'X-Frame-Options': 'DENY', 'Referrer-Policy': 'no-referrer',
                'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'"})
        return response

    async def bootstrap(request):
        return web.json_response(dict(v=1, transport='bridge', simulator=simulator, token=token, lease_ms=6000,
                                      recording='bridge' if controller.recording else False, observers=True))

    def require_token(request):
        if not secrets.compare_digest(request.headers.get('X-PitPat-Token', ''), token):
            raise web.HTTPForbidden()
        if not controller.recording:
            raise web.HTTPServiceUnavailable(text='Shared recording unavailable')
        return controller.recording.recorder.store

    async def walks(request):
        store = require_token(request)
        try:
            limit = int(request.query.get('limit', '50'))
            result = await asyncio.to_thread(store.page, limit, request.query.get('before'))
        except ValueError as exc: raise web.HTTPBadRequest(text=str(exc)) from None
        return web.json_response(result)

    async def import_walks(request):
        store = require_token(request)
        actual_port = port or request.transport.get_extra_info('sockname')[1]
        if request.headers.get('Origin') != f'http://127.0.0.1:{actual_port}':
            raise web.HTTPForbidden()
        if request.content_type != 'application/json': raise web.HTTPUnsupportedMediaType()
        try:
            data = load_json(await request.text())
            if not isinstance(data, dict) or set(data) != {'walks'}: raise ValueError('Expected walks list')
            result = await asyncio.to_thread(store.merge, data['walks'])
        except (ValueError, TypeError, RecursionError) as exc:
            raise web.HTTPConflict(text=str(exc)) from None
        return web.json_response(result)

    async def assets(request):
        name = ASSETS.get(request.path)
        if not name or not (ROOT / name).is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(ROOT / name)

    async def websocket(request):
        actual_port = port or request.transport.get_extra_info('sockname')[1]
        if request.headers.get('Origin') != f'http://127.0.0.1:{actual_port}':
            raise web.HTTPForbidden()
        if len(sockets) >= 16:
            raise web.HTTPServiceUnavailable()
        ws = web.WebSocketResponse(max_msg_size=16384, receive_timeout=None)
        await ws.prepare(request)
        sockets.add(ws)
        client_id = secrets.token_hex(16)
        outgoing = asyncio.Queue(maxsize=64)
        pending = set()
        unsubscribe = lambda: None
        writer = None
        overflow = False

        def send(message):
            nonlocal overflow
            if ws.closed or overflow:
                return
            try:
                outgoing.put_nowait(message)
            except asyncio.QueueFull:
                overflow = True
                asyncio.create_task(ws.close(code=1008, message=b'Slow consumer'))
                controller.spawn(controller.client_lost(client_id))

        async def write_messages():
            while True:
                await ws.send_json(await outgoing.get())

        def relay(message):
            send(dict(message, snapshot=controller.snapshot_for(client_id)))

        async def command(data):
            try:
                result = await controller.dispatch(client_id, data)
                send(dict(v=1, id=data['id'], generation=controller.generation, ok=True, result=result))
            except Exception as error:
                message = str(error) if isinstance(error, ValueError) else 'Local Bluetooth operation failed; check adapter and connection.'
                send(dict(v=1, id=data['id'], generation=controller.generation, ok=False, error=message))

        try:
            first = await asyncio.wait_for(ws.receive(), AUTH_TIMEOUT)
            data = load_json(first.data) if first.type == WSMsgType.TEXT else None
            if (not isinstance(data, dict) or set(data) != {'v', 'op', 'token'} or
                type(data['v']) is not int or data['v'] != 1 or data['op'] != 'authorize' or
                not isinstance(data['token'], str) or not secrets.compare_digest(data['token'], token)):
                await ws.close(code=1008, message=b'Authorization failed')
                return ws
            controller.register_client(client_id, 'browser')
            await ws.send_json(dict(v=1, event='authorized', generation=controller.generation, simulator=simulator,
                                    snapshot=controller.snapshot_for(client_id)))
            writer = asyncio.create_task(write_messages())
            unsubscribe = controller.subscribe(relay)
            async for message in ws:
                if message.type != WSMsgType.TEXT:
                    break
                try:
                    data = load_json(message.data)
                    validate_request(data)
                    if len(pending) >= 8:
                        raise ValueError('Too many pending requests')
                except (ValueError, TypeError, RecursionError):
                    send(dict(v=1, ok=False, error='Invalid or excessive request'))
                    continue
                task = asyncio.create_task(command(data))
                pending.add(task)
                task.add_done_callback(pending.discard)
        except (ValueError, TypeError, TimeoutError, RecursionError):
            await ws.close(code=1008, message=b'Authorization failed')
        finally:
            unsubscribe()
            await controller.unregister_client(client_id)
            if pending:
                # In particular, let a late connect finish and independently Stop.
                await asyncio.gather(*pending, return_exceptions=True)
            if writer:
                writer.cancel()
                await asyncio.gather(writer, return_exceptions=True)
            sockets.discard(ws)
            await ws.close()
        return ws

    async def watchdog():
        while True:
            await asyncio.sleep(0.25)
            await controller.tick()

    async def lifecycle(app):
        if controller.recording:
            await controller.recording.recorder.initialize()
        if native: await native.serve()
        task = asyncio.create_task(watchdog())
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        if native: await native.close()
        await controller.shutdown()

    async def close_sockets(app):
        await asyncio.gather(*(socket.close(code=1001, message=b'Service shutting down') for socket in tuple(sockets)))

    app = web.Application(middlewares=[restrict], client_max_size=4 * 1024 * 1024)
    app.router.add_get('/api/bootstrap', bootstrap)
    app.router.add_get('/api/ws', websocket)
    app.router.add_get('/api/walks', walks)
    app.router.add_post('/api/walks/import', import_walks)
    app.router.add_get('/{path:.*}', assets)
    app.on_shutdown.append(close_sockets)
    app.cleanup_ctx.append(lifecycle)
    return app
