import pandas as pd
import numpy as np
import json


def identifier_to_name(mapping: dict, ident: int | str) -> str | None:
    _ident = f"{ident}" if type(ident) is int else ident
    for name in mapping:
        if mapping[name] == _ident:
            return name

    return None


with open('../data/demo_trace_1.json', 'r') as h:
    data = json.load(h)

with open('demo_trace_pretty_2.json', 'w') as h:
    h.write(json.dumps(data, indent=4))

with open('../var_idents.json', 'r') as h:
    identifier_mappings = json.load(h)

game_events = []

for elem in data:
    if 'messages' in elem:
        for msg_event in elem['messages']:
            if 'event' in msg_event or 'event_type_id' in msg_event:
                game_events.append(msg_event)


cmds = {}
keys = set()
for elem in data:
    for key in elem.keys():
        keys.add(key)

    if 'messages' in elem:
        _ft = 0
        for msg_event in elem['messages']:
            if 'frame_time' in msg_event:
                _ft = msg_event['frame_time']
                continue

            cmds[_ft] = []
            if 'entities' not in msg_event:
                continue

            for entity in msg_event['entities']:
                for prop in entity['props']:
                    cmds[_ft].append(
                        {
                            'name': identifier_to_name(identifier_mappings, prop['identifier']),
                            'index': prop['index'],
                            'value': prop['value']
                        }
                    )
            # print(msg_event)
print(cmds)
print(list(keys))
