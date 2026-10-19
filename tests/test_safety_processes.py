import asyncio,unittest
from tests import safety_harness
class ProcessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(hasattr(safety_harness,'ProcessPairFixture'),'persistent independent plant fixture missing')
        self.pair=safety_harness.ProcessPairFixture();await self.pair.start();await self.pair.start_minimum()
    async def asyncTearDown(self):
        if hasattr(self,'pair'):await self.pair.close()
    async def test_application_crash_stops_persistent_plant(self):
        await self.pair.kill_application();await self.pair.until_stopped(2.55)
        self.assertEqual(self.pair.plant.speed,0);self.assertIsNone(self.pair.safety.poll())
        self.assertIsNotNone((await self.pair.snapshot())['fault_id'])
    async def test_application_freeze_stops_and_resumption_does_not_restart(self):
        await self.pair.freeze_application();await self.pair.until_stopped(2.55)
        self.assertEqual(self.pair.plant.speed,0)
        await self.pair.resume_application();await asyncio.sleep(.3)
        self.assertEqual(self.pair.plant.speed,0)
        self.assertEqual((await self.pair.snapshot())['authorization_state'],'fault-latched')
    async def test_resumed_application_reconnects_without_discovery_or_motion(self):
        await self.pair.freeze_application();await self.pair.until_stopped(2.55)
        fault=(await self.pair.snapshot())['fault_id']
        await self.pair.resume_application()
        deadline=asyncio.get_running_loop().time()+3
        while True:
            view=await self.pair.app_request('observe')
            if view['safety_available'] and view['fault_id']==fault:break
            self.assertLess(asyncio.get_running_loop().time(),deadline,
                            'Resumed application did not expose safety recovery without discovery')
            await asyncio.sleep(.05)
        self.assertTrue(view['recovery']);self.assertTrue(view['blocked'])
        self.assertFalse(view['is_owner']);self.assertIsNone(view['owner_kind'])
        self.assertEqual(view['session']['status'],'interrupted')
        self.assertEqual(self.pair.plant.speed,0)
        self.assertTrue((await self.pair.snapshot())['bridge_healthy'])
        with self.assertRaises(ValueError):await self.pair.app_request('start',{'speed':1000})
        self.assertEqual(self.pair.plant.speed,0)

    async def test_safety_crash_does_not_look_like_automatic_stop(self):
        await self.pair.kill_safety();await asyncio.sleep(.2)
        self.assertEqual(self.pair.plant.speed,1000)
        self.assertIsNone(self.pair.application.poll())
    async def test_safety_freeze_leaves_plant_moving_and_application_blocks(self):
        await self.pair.freeze_safety();await asyncio.sleep(2.3)
        self.assertEqual(self.pair.plant.speed,1000)
        result=await self.pair.app_request('observe')
        self.assertFalse(result['safety_available']);self.assertTrue(result['blocked'])
    async def test_emergency_helper_stops_while_application_frozen(self):
        from bridge.desktop import safety_stop
        await self.pair.freeze_application()
        await safety_stop(self.pair.runtime)
        self.assertEqual(self.pair.plant.speed,0)
    async def test_explicit_recovery_after_application_resume(self):
        await self.pair.freeze_application();await self.pair.until_stopped(2.55)
        await self.pair.resume_application();await asyncio.sleep(.3)
        await self.pair.app_request('connect',{'recover':True})
        view=await self.pair.app_request('observe')
        if view.get('session',{}):
            if view['session']['status']=='interrupted':
                await self.pair.app_request('resolve_session',{'session_id':view['session']['sessionId'],'choice':'new'})
        await self.pair.app_request('stop');view=await self.pair.app_request('observe')
        await self.pair.app_request('acknowledge_recovery',{'fault_id':view['fault_id'],'stop_confirmation_id':view['stop_confirmation_id']})
        self.assertEqual(self.pair.plant.speed,0)
        await self.pair.app_request('start',{'speed':1000})
        await self.pair.until(lambda:self.pair.plant.speed==1000,1)
