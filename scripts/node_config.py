"""The native host's reviewed public node publisher binding."""
import json
import re


def node_source(root):
    source = json.loads((root / 'packaging/node.json').read_text())
    if (set(source) != {'origin', 'app_id', 'key_id', 'public_key'}
            or source['origin'] != 'https://api.waozi.xyz'
            or source['app_id'] != 'inbe.arcade'
            or not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,62}', source['key_id'])
            or not re.fullmatch(r'[a-f0-9]{64}', source['public_key'])):
        raise ValueError('Invalid reviewed node publisher binding')
    sequence = json.loads((root / 'apps/versions.json').read_text())['node_apps']['arcade']['sequence']
    if type(sequence) is not int or not 1 <= sequence <= 2147483647:
        raise ValueError('Invalid catalog release floor')
    return source | {'minimum_sequence': sequence}
