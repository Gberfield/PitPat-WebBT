import unittest
from bridge import safety_messages as wire
class MessageTests(unittest.TestCase):
    def test_review_requires_strict_boolean_and_revision(self):
        frame=dict(v=1,id='r',op='recording_review',authority=dict(safety_id='s',link_epoch=1,fault_generation=0,bridge_id='b',grant_id=None,command_seq=0),args=dict(review=True,revision=0))
        self.assertEqual(wire.validate_frame(frame,'application'),frame)
        for args in (dict(review=1,revision=0),dict(review=True,revision=True),dict(review=False,revision=-1),dict(review=False),dict(review=True,revision=1,extra=None)):
            with self.subTest(args=args),self.assertRaises(ValueError):wire.validate_frame(dict(frame,args=args),'application')
        with self.assertRaises(ValueError):wire.validate_frame(dict(frame,authority=None),'helper')
    def test_helper_cannot_move(self):
        self.assertTrue(hasattr(wire,'validate_frame'), 'safety IPC schema missing')
        with self.assertRaises(ValueError):wire.validate_frame(dict(v=1,id='x',op='start',authority=None,args={'speed':1000}),'helper')
    def test_helper_stop_is_well_formed(self):
        self.assertTrue(hasattr(wire,'validate_frame'), 'safety IPC schema missing')
        frame=dict(v=1,id='x',op='stop',authority=None,args={})
        self.assertEqual(wire.validate_frame(frame,'helper'),frame)
    def test_invalid_authority_and_nonfinite_input(self):
        from bridge.messages import load_json
        for text in ('{"v":1,"v":1}','{"v":NaN}'):
            with self.assertRaises(ValueError):load_json(text)
        frame=dict(v=1,id='x',op='start',authority=dict(safety_id='s',link_epoch=True,fault_generation=0,bridge_id='b',grant_id='g',command_seq=1),args={'speed':1000})
        with self.assertRaises(ValueError):wire.validate_frame(frame,'application')
        frame['authority']['link_epoch']=1;frame['args']['speed']=1050
        with self.assertRaises(ValueError):wire.validate_frame(frame,'application')
