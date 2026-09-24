"""SRD 5.2.1 mechanical primitives. No network, persistence, or client RNG."""
from __future__ import annotations
from typing import Callable

Draw = Callable[[int, int], int]


def roll(draw: Draw, sides: int, count: int = 1) -> list[int]:
    if type(sides) is not int or type(count) is not int or not 2 <= sides <= 100 or not 1 <= count <= 40:
        raise ValueError('invalid dice expression')
    values = [draw(1, sides) for _ in range(count)]
    if any(type(value) is not int or not 1 <= value <= sides for value in values):
        raise ValueError('dice source returned an invalid result')
    return values


def d20(draw: Draw, modifier: int, *, advantage: bool = False, disadvantage: bool = False,
        dc: int | None = None, attack: bool = False, reroll_one: bool = False) -> dict:
    """SRD pp. 6-8: opposing advantage sources cancel, regardless of their counts."""
    mode = 'normal' if bool(advantage) == bool(disadvantage) else 'advantage' if advantage else 'disadvantage'
    dice = roll(draw, 20, 1 if mode == 'normal' else 2)
    original = list(dice)
    natural = min(dice) if mode == 'disadvantage' else max(dice)
    if reroll_one and natural == 1:
        dice[dice.index(1)] = roll(draw, 20)[0]
        natural = min(dice) if mode == 'disadvantage' else max(dice)
    result = {'dice': dice, 'mode': mode, 'natural': natural, 'modifier': modifier, 'total': natural + modifier}
    if original != dice:
        result['initial_dice'] = original
    if dc is not None:
        result['success'] = natural == 20 or (natural != 1 and natural + modifier >= dc) if attack else natural + modifier >= dc
    result['critical'] = bool(attack and natural == 20)
    return result


def damage_amount(raw: int, *, reduction: int = 0, resistant: bool = False,
                  vulnerable: bool = False, immune: bool = False) -> int:
    """SRD p.17: numeric adjustments, resistance (round down), then vulnerability."""
    if type(raw) is not int or type(reduction) is not int or raw < 0 or reduction < 0:
        raise ValueError('damage must be nonnegative integers')
    value = max(0, raw - reduction)
    if immune:
        return 0
    if resistant:
        value //= 2
    return value * 2 if vulnerable else value


def unconscious(actor: dict) -> bool:
    return actor.get('dead', False) or 'unconscious' in actor['conditions'] or actor['hp'] == 0


def incapacitated(actor: dict) -> bool:
    return unconscious(actor) or 'incapacitated' in actor['conditions']


def lose_hp(actor: dict, amount: int, *, critical: bool = False, knockout: bool = False) -> dict:
    """SRD pp.17-18. Knockout is the 2024/SRD5.2 rule (1 HP), not legacy 0 HP."""
    if type(amount) is not int or amount < 0:
        raise ValueError('invalid damage')
    before = actor['hp']
    if actor.get('dead') or amount == 0:
        return {'hp_before': before, 'hp_after': before, 'temporary_absorbed': 0}
    absorbed = min(actor.get('temp_hp', 0), amount)
    actor['temp_hp'] = actor.get('temp_hp', 0) - absorbed
    remaining = amount - absorbed
    if knockout and before > 0 and remaining >= before:
        actor['hp'] = 1
        actor['conditions'] = sorted(set(actor['conditions']) | {'unconscious', 'prone'})
        actor['knocked_out'] = True
    elif before == 0:
        # Damage at zero HP is damage even when temporary HP absorbs it.
        actor['stable'] = False
        if remaining >= actor['max_hp']:
            actor['dead'] = True
        else:
            actor['death_failures'] += 2 if critical else 1
            actor['dead'] = actor['death_failures'] >= 3
    else:
        actor['hp'] = max(0, before - remaining)
        if actor['hp'] == 0:
            actor['dead'] = not actor.get('death_saves', False) or remaining - before >= actor['max_hp']
            actor['conditions'] = sorted(set(actor['conditions']) | {'unconscious', 'prone'})
            actor['stable'] = False
    if incapacitated(actor):
        actor['dodge'] = False
    return {'hp_before': before, 'hp_after': actor['hp'], 'temporary_absorbed': absorbed,
            'dead': actor.get('dead', False), 'knocked_out': actor.get('knocked_out', False)}


def heal(actor: dict, amount: int) -> int:
    if type(amount) is not int or amount < 0:
        raise ValueError('invalid healing')
    if actor.get('dead') or amount == 0:
        return 0
    old = actor['hp']
    actor['hp'] = min(actor['max_hp'], old + amount)
    if actor['hp'] > 0:
        actor['conditions'] = [condition for condition in actor['conditions'] if condition != 'unconscious']
        actor['stable'] = False
        actor['knocked_out'] = False
        actor['death_successes'] = actor['death_failures'] = 0
    return actor['hp'] - old


def death_save(actor: dict, draw: Draw) -> dict:
    """Primitive for the later PC slice; not an exposed M1 combat action."""
    if actor['hp'] != 0 or actor.get('dead') or actor.get('stable'):
        raise ValueError('no death saving throw is due')
    natural = roll(draw, 20)[0]
    if natural == 20:
        heal(actor, 1)
    elif natural == 1:
        actor['death_failures'] += 2
    elif natural >= 10:
        actor['death_successes'] += 1
    else:
        actor['death_failures'] += 1
    if actor['death_failures'] >= 3:
        actor['dead'] = True
    if actor['death_successes'] >= 3:
        actor['stable'] = True
        actor['death_successes'] = actor['death_failures'] = 0
    return {'natural': natural, 'hp': actor['hp'], 'stable': actor.get('stable', False), 'dead': actor.get('dead', False)}


def melee_attack(attacker: dict, target: dict, draw: Draw, *, knockout: bool = False, use_luck: bool = True) -> dict:
    """Fixed equipped weapon, visible targets, no cover: closed M1 scene assumptions."""
    if incapacitated(attacker) or target.get('dead'):
        raise ValueError('invalid combatant')
    close = max(abs(a-b) for a, b in zip(attacker['position'], target['position'])) <= 1
    if not close:
        raise ValueError('outside 5-foot reach')
    advantage = 'prone' in target['conditions'] or unconscious(target)
    disadvantage = 'prone' in attacker['conditions'] or bool(attacker.get('sapped_by')) or (target.get('dodge', False) and not incapacitated(target) and target['speed'] > 0)
    test = d20(draw, attacker['attack_bonus'], advantage=advantage, disadvantage=disadvantage, dc=target['ac'], attack=True, reroll_one=attacker.get('lucky', False) and use_luck)
    attacker.pop('sapped_by', None)
    critical = test['success'] and (test['critical'] or unconscious(target))
    result = {'attack': test, 'hit': test['success'], 'critical': bool(critical), 'damage': 0, 'damage_dice': []}
    if test['success']:
        dice = roll(draw, attacker['damage_die'], 2 if critical else 1)
        raw = max(0, sum(dice) + attacker['damage_bonus'])
        kind = attacker['damage_type']
        damage = damage_amount(raw, resistant=kind in target.get('resistances', []),
                               vulnerable=kind in target.get('vulnerabilities', []), immune=kind in target.get('immunities', []))
        result.update(damage_dice=dice, damage_bonus=attacker['damage_bonus'], damage_type=kind, raw_damage=raw, damage=damage)
        result['effect'] = lose_hp(target, damage, critical=bool(critical), knockout=knockout)
        if attacker.get('mastery') == 'sap' and not target.get('dead'):
            target['sapped_by'] = attacker['id']
            result['mastery'] = 'sap'
    return result
