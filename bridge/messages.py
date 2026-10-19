"""Strict versioned requests shared by browser and native boundaries."""
import json

ALLOWED = {'discover': set(), 'connect': {'device_id', 'recover'}, 'renew': set(),
           'start': {'speed'}, 'pause': {'speed'}, 'set_speed': {'speed'},
           'stop': set(), 'stop_disconnect': set(), 'release': set(),
           'observe': set(), 'take_control': set(), 'resolve_session': {'session_id','choice'}}


def load_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def validate_request(data):
    if (not isinstance(data, dict) or set(data) != {'v', 'id', 'op', 'generation', 'args'} or
            type(data['v']) is not int or data['v'] != 1 or
            not isinstance(data['id'], str) or not 1 <= len(data['id']) <= 64 or
            type(data['generation']) is not int or data['generation'] < 0 or
            not isinstance(data['op'], str) or data['op'] not in ALLOWED or
            not isinstance(data['args'], dict) or set(data['args']) - ALLOWED[data['op']]):
        raise ValueError('Invalid request schema')
    args = data['args']
    if data['op'] == 'connect':
        if set(args) == {'recover'} and args['recover'] is True:
            return
        if set(args) != {'device_id'} or not isinstance(args['device_id'], str) or len(args['device_id']) > 128:
            raise ValueError('Invalid device selection')
    if data['op'] == 'set_speed' and 'speed' not in args:
        raise ValueError('Speed is required')

    if 'speed' in args:
        speed = args['speed']
        if type(speed) is not int or not 1000 <= speed <= 6000 or speed % 100:
            raise ValueError('Invalid speed')
    if data['op'] == 'resolve_session':
        if (set(args) != {'session_id', 'choice'} or not isinstance(args['session_id'], str)
                or not 1 <= len(args['session_id']) <= 128 or args['choice'] not in ('continue', 'new')):
            raise ValueError('Invalid continuity choice')
