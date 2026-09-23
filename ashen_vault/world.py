"""World SDK adapter. All SRD decisions stay in this package, not the kernel."""
from __future__ import annotations
from agent_world import WorldDefinition, FunctionSpec, StateRule, FunctionOutcome, ViewSpec, StreamSpec, StreamEvent
from agent_world.errors import RuleViolation
from .content import initial_state, ARENA, PROFILES
from .engine import apply, active, RulesError


def schema(properties=None, required=()):
    return {'type': 'object', 'properties': properties or {}, 'required': list(required), 'additionalProperties': False}


EMPTY = schema()
TURN = {'type': 'integer', 'minimum': 1}
CELL = {'type': 'array', 'items': {'type': 'integer', 'minimum': 0, 'maximum': 100}, 'minItems': 2, 'maxItems': 2}
SEAT = {'type': 'string', 'enum': list(PROFILES)}
STATE = schema({
    'ruleset': {'const': 'SRD-5.2.1'}, 'milestone': {'const': 'M1-melee-laboratory'},
    'phase': {'enum': ['lobby', 'active', 'complete']},
    'owners': {'type': 'object', 'additionalProperties': {'type': 'string'}},
    'actors': {'type': 'object', 'additionalProperties': {'type': 'object'}},
    'order': {'type': 'array', 'items': SEAT, 'maxItems': 2, 'uniqueItems': True},
    'initiative': {'type': 'object'}, 'index': {'type': 'integer', 'minimum': 0, 'maximum': 1},
    'round': {'type': 'integer', 'minimum': 0}, 'turn_id': {'type': 'integer', 'minimum': 0},
    'pending': {'type': ['object', 'null']}, 'window_serial': {'type': 'integer', 'minimum': 0},
    'winner': {'type': ['string', 'null']},
}, tuple(initial_state()))


def initialize(ctx):
    ctx.set_state('encounter', 'state', initial_state())


def read(ctx):
    return ctx.get_state('encounter', 'state')


def seat_for(state, role_id):
    return next((seat for seat, owner in state['owners'].items() if owner == role_id), None)


def join(ctx, args):
    state = read(ctx)
    seat = args['seat']
    current = seat_for(state, ctx.actor_role_id)
    if current is not None:
        if current != seat:
            raise RuleViolation('AlreadyBoundToAnotherSeat')
        return FunctionOutcome({'seat': seat, 'already_joined': True})
    if state['phase'] != 'lobby' or seat in state['owners']:
        raise RuleViolation('SeatUnavailable')
    state['owners'][seat] = ctx.actor_role_id
    ctx.set_state('encounter', 'state', state)
    return FunctionOutcome({'seat': seat}, (StreamEvent('combat', 'seat_joined', {'seat': seat}, key='join'),))


def participant(ctx, args):
    return seat_for(read(ctx), ctx.actor_role_id) is not None


def handler(command):
    def run(ctx, args):
        state = read(ctx)
        seat = seat_for(state, ctx.actor_role_id)
        try:
            updated, result = apply(state, seat, command, args, ctx.random_int)
        except RulesError as exc:
            raise RuleViolation(str(exc)) from None
        ctx.set_state('encounter', 'state', updated)
        report = {'command': command, 'actor': seat, 'result': result, 'round': updated['round'],
                  'turn_id': updated['turn_id'], 'active': active(updated), 'phase': updated['phase']}
        return FunctionOutcome(report, (StreamEvent('combat', 'rules_resolved', report, key='resolution'),))
    return run


def bootstrap(ctx):
    state = read(ctx)
    return {'scene': state, 'your_seat': seat_for(state, ctx.actor_role_id), 'arena': ARENA,
            'coverage': 'M1: fixed melee NPC profiles; no PC classes, spells, ranged attacks, or open DM adjudication.'}


def look(ctx, args):
    return FunctionOutcome(bootstrap(ctx))


def scene(ctx, args):
    state = read(ctx)
    # This rule laboratory deliberately publishes combat stats, never identity tokens.
    pending = state['pending']
    return {'entities': state['actors'], 'meta': {'phase': state['phase'], 'round': state['round'],
            'turn_id': state['turn_id'], 'active': active(state), 'order': state['order'],
            'pending': pending, 'winner': state['winner'], 'arena': ARENA,
            'ruleset': state['ruleset'], 'milestone': state['milestone']}}


SPECS = [
    FunctionSpec('vault.join', join, schema({'seat': SEAT}, ('seat',)),
                 description='Bind your current identity to one unoccupied NPC fixture seat. Never creates an identity.'),
    FunctionSpec('vault.look', look, EMPTY, access='read', description='Read server scene, your seat, turn_id, and any reaction window.'),
    FunctionSpec('vault.begin', handler('begin'), EMPTY, authorize=participant,
                 description='Begin once both identity holders have independently joined. Server rolls initiative.'),
]
for command in ('dash', 'dodge', 'disengage', 'drop_prone', 'stand', 'end_turn'):
    SPECS.append(FunctionSpec('vault.'+command, handler(command), schema({'turn_id': TURN}, ('turn_id',)),
                             authorize=participant, description=f'{command}: use the observed turn_id. Server verifies turn and action budget.'))
SPECS.extend([
    FunctionSpec('vault.move', handler('move'), schema({'turn_id': TURN, 'path': {'type': 'array', 'items': CELL, 'minItems': 1, 'maxItems': 12}}, ('turn_id', 'path')),
                 authorize=participant, description='Choose a tactical path of adjacent 5-foot cells, not animation. May pause BEFORE leaving reach; awaiting_reaction is not arrival.'),
    FunctionSpec('vault.attack', handler('attack'), schema({'turn_id': TURN, 'target': SEAT, 'knockout': {'type': 'boolean'}}, ('turn_id', 'target')),
                 authorize=participant, description='One equipped melee attack. Only target and optional knockout intent; no client dice, hit, damage or advantage fields.'),
    FunctionSpec('vault.react', handler('react'), schema({'window_id': {'type': 'string', 'maxLength': 64}, 'choice': {'enum': ['attack', 'decline']}, 'knockout': {'type': 'boolean'}}, ('window_id', 'choice')),
                 authorize=participant, description='Only the offered reactor can respond to the current window, including OFF TURN. Declining does not spend a reaction.'),
])
WORLD = WorldDefinition('ashen-vault', 'Ashen Vault M1', tuple(SPECS), state_rules=(StateRule('encounter', 'state', STATE),),
    initialize=initialize, bootstrap=bootstrap,
    views=(ViewSpec('battle', scene, public=True, streams=('combat',)),),
    streams=(StreamSpec('combat', public=True, max_events=512, retention_seconds=86400),),
    entry_instructions='SRD5.2.1 M1 melee laboratory, not complete 5E. Inspect vault.look, join one open seat yourself, then begin with both ready. '
    'Only act with the observed turn_id; off-turn vault.react is legal ONLY for its offered window. Reuse operation_id for retry, never reroll. '
    'No spells, class characters or ranged attacks are implemented. Never invent outcomes; the authoritative dice and results are in receipts.')
