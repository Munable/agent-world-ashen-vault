"""A closed melee encounter. Unsupported 5E options are not silently approximated."""
from __future__ import annotations
from copy import deepcopy
from .content import ARENA
from .rules import Draw, d20, incapacitated, melee_attack


class RulesError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RulesError(message)


def active(state: dict) -> str | None:
    return state['order'][state['index']] if state['phase'] == 'active' else None


def adjacent(a: list[int], b: list[int]) -> bool:
    return max(abs(a[0]-b[0]), abs(a[1]-b[1])) == 1


def clear_step(a: list[int], b: list[int]) -> bool:
    if b in ARENA['walls'] or not (0 <= b[0] < ARENA['width'] and 0 <= b[1] < ARENA['height']):
        return False
    if a[0] != b[0] and a[1] != b[1]:
        return [a[0], b[1]] not in ARENA['walls'] and [b[0], a[1]] not in ARENA['walls']
    return True


def _turn_start(state: dict) -> None:
    actor = state['actors'][active(state)]
    actor.update(action=True, reaction=True, dodge=False, disengage=False, movement=actor['speed'])
    if 'bonus_action' in actor:
        actor['bonus_action'] = True
        actor['extra_actions'] = 0
    for other in state['actors'].values():
        if other.get('sapped_by') == actor['id']:
            other.pop('sapped_by', None)
    state['turn_id'] += 1


def _finish(state: dict) -> None:
    live = [key for key, actor in state['actors'].items() if not incapacitated(actor)]
    if len(live) <= 1:
        state.update(phase='complete', winner=live[0] if live else None, pending=None)


def _cost(state: dict, actor: dict, position: list[int]) -> int:
    others = [other for other in state['actors'].values() if other['id'] != actor['id'] and other['position'] == position]
    difficult = position in ARENA['difficult'] or any(other['team'] != actor['team'] for other in others)
    return 5 + (5 if difficult else 0) + (5 if 'prone' in actor['conditions'] else 0)


def _validate_path(state: dict, actor: dict, path: list) -> None:
    require(isinstance(path, list) and 1 <= len(path) <= 12, 'InvalidPath: provide 1..12 adjacent cells')
    cursor = actor['position']
    cost = 0
    for cell in path:
        require(isinstance(cell, list) and len(cell) == 2 and all(type(x) is int for x in cell), 'InvalidCell')
        require(adjacent(cursor, cell) and clear_step(cursor, cell), 'InvalidPath: blocked or non-adjacent step')
        for other in state['actors'].values():
            if other['id'] != actor['id'] and other['position'] == cell:
                require(other['team'] == actor['team'] or incapacitated(other) or (actor.get('nimble') and actor.get('size') == 'small' and other.get('size', 'medium') != 'small'), 'OccupiedByEnemy')
        cost += _cost(state, actor, cell)
        cursor = cell
    require(not any(other['id'] != actor['id'] and other['position'] == cursor for other in state['actors'].values()), 'OccupiedDestination')
    require(cost <= actor['movement'], 'InsufficientMovement')


def _advance_movement(state: dict, actor_id: str, path: list, waived: list[str] | None = None) -> dict:
    actor = state['actors'][actor_id]
    traveled = []
    for index, cell in enumerate(path):
        if not actor['disengage']:
            for other_id, other in state['actors'].items():
                if (other_id != actor_id and other_id not in (waived or []) and other['team'] != actor['team']
                        and other['reaction'] and not incapacitated(other)
                        and adjacent(other['position'], actor['position'])
                        and clear_step(other['position'], actor['position'])
                        and max(abs(other['position'][i]-cell[i]) for i in (0,1)) > 1):
                    state['window_serial'] += 1
                    state['pending'] = {'window_id': f"oa-{state['turn_id']}-{state['window_serial']}",
                        'reactor': other_id, 'mover': actor_id, 'path': deepcopy(path[index:]),
                        'waived': list(waived or [])}
                    return {'status': 'awaiting_reaction', 'traveled': traveled,
                            'window_id': state['pending']['window_id'], 'reactor': other_id}
        actor['movement'] -= _cost(state, actor, cell)
        actor['position'] = list(cell)
        traveled.append(list(cell))
        waived = []
    state['pending'] = None
    return {'status': 'arrived', 'traveled': traveled, 'position': actor['position']}


def apply(state: dict, actor_id: str, command: str, args: dict, draw: Draw) -> tuple[dict, dict]:
    """Return a fresh state; rejection never changes the caller's state."""
    state = deepcopy(state)
    require(actor_id in state['actors'], 'UnknownActor')
    actor = state['actors'][actor_id]
    if command == 'begin':
        require(state['phase'] == 'lobby', 'EncounterAlreadyStarted')
        require(set(state['owners']) == set(state['actors']), 'WaitingForParticipants')
        state['initiative'] = {key: d20(draw, value['initiative_bonus'], reroll_one=value.get('lucky', False)) for key, value in sorted(state['actors'].items())}
        # Both are NPC fixtures; the authored DM tie policy is fixed seat order.
        state['order'] = sorted(state['actors'], key=lambda key: (-state['initiative'][key]['total'], key))
        state.update(phase='active', round=1, index=0)
        _turn_start(state)
        return state, {'initiative': state['initiative'], 'order': state['order']}
    require(state['phase'] == 'active', 'EncounterNotActive')
    if command == 'react':
        pending = state['pending']
        require(pending is not None and args.get('window_id') == pending['window_id'], 'StaleReactionWindow')
        require(actor_id == pending['reactor'], 'NotYourReaction')
        require(args.get('choice') in ('attack', 'decline'), 'UnsupportedReaction')
        require(actor['reaction'] and not incapacitated(actor), 'ReactionUnavailable')
        mover = state['actors'][pending['mover']]
        result = {'choice': args['choice'], 'reactor': actor_id, 'mover': pending['mover'], 'window_id': pending['window_id']}
        if args['choice'] == 'attack':
            actor['reaction'] = False
            result['attack_result'] = melee_attack(actor, mover, draw, knockout=args.get('knockout', False), use_luck=args.get('use_luck', True))
        _finish(state)
        if state['phase'] == 'complete' or incapacitated(mover):
            state['pending'] = None
            result['movement'] = {'status': 'interrupted', 'position': mover['position']}
        else:
            result['movement'] = _advance_movement(state, pending['mover'], pending['path'], pending['waived'] + [actor_id])
        return state, result
    require(state['pending'] is None, 'ReactionPending: resolve the visible window before continuing')
    require(active(state) == actor_id, 'NotYourTurn')
    require(args.get('turn_id') == state['turn_id'], 'StaleTurn')
    require(not incapacitated(actor), 'Incapacitated')
    if command == 'move':
        path = args['path']
        _validate_path(state, actor, path)
        return state, _advance_movement(state, actor_id, path)
    if command == 'drop_prone':
        require(actor['speed'] > 0, 'SpeedIsZero')
        actor['conditions'] = sorted(set(actor['conditions']) | {'prone'})
        return state, {'condition': 'prone'}
    if command == 'stand':
        require('prone' in actor['conditions'], 'NotProne')
        cost = actor['speed'] // 2
        require(actor['speed'] > 0 and actor['movement'] >= cost, 'InsufficientMovement')
        actor['movement'] -= cost
        actor['conditions'].remove('prone')
        return state, {'movement_cost': cost}
    if command == 'end_turn':
        actor['disengage'] = False
        state['index'] = (state['index'] + 1) % len(state['order'])
        if state['index'] == 0:
            state['round'] += 1
        _turn_start(state)
        return state, {'status': 'turn_advanced'}
    require(command in ('attack', 'dash', 'dodge', 'disengage'), 'UnsupportedRule')
    require(actor['action'], 'ActionSpent')
    if command == 'attack':
        target_id = args.get('target')
        require(target_id in state['actors'] and target_id != actor_id, 'InvalidTarget')
        target = state['actors'][target_id]
        require(not target['dead'], 'TargetDead')
        require(adjacent(actor['position'], target['position']) and clear_step(actor['position'], target['position']), 'OutOfReachOrBlocked')
        result = {'actor': actor_id, 'target': target_id, **melee_attack(actor, target, draw, knockout=args.get('knockout', False), use_luck=args.get('use_luck', True))}
        _finish(state)
    elif command == 'dash':
        actor['movement'] += actor['speed']
        result = {'extra_movement': actor['speed']}
    else:
        actor[command] = True
        result = {'effect': command}
    if actor.get('extra_actions', 0):
        actor['extra_actions'] -= 1
    else:
        actor['action'] = False
    return state, result
