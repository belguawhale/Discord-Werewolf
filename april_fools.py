import json

def get_default_mapping():
    return {
        'stats': 'myrole',
        'myrole': 'stats',

        'join': 'info',
        'j': 'info',
        'info': 'join',

        'wait': 'start',
        'w': 'start',
        'start': 'leave',
        'leave': 'wait',
        'q': 'wait',

        'lynch': 'retract',
        'vote': 'retract',
        'votes': 'retract',
        'v': 'retract',
        'retract': 'v',
        'r': 'v',

        'shoot': 'ping',
        'ping': 'shoot',

        'time': 'list',
        't': 'list',
        'list': 'time',

        'role': 'game',
        'roles': 'game',
        'game': 'totem',
        'gamemode': 'totem',
        'gamemodes': 'totem',
        'totem': 'role',
        'totems': 'role',

        'coin': 'abs',
        'cat': 'coin',
        'abstain': 'cat',
        'abs': 'cat',
        'nl': 'cat',
    }

def new_mapping(old, new):
    BASE_COMMAND_MAPPING[old] = new

def unset_mapping(key):
    try:
        del BASE_COMMAND_MAPPING[key]
    except KeyError:
        pass

def reset_mapping(key):
    try:
        BASE_COMMAND_MAPPING[key] = get_default_mapping()[key]
    except KeyError:
        pass

BASE_COMMAND_MAPPING = get_default_mapping()
