"""Original gatehouse fixture; numerical attack profiles referenced to SRD 5.2.1."""
from copy import deepcopy

ARENA = {'width': 14, 'height': 8, 'feet_per_cell': 5, 'lighting': 'bright',
         'walls': [[5, 4], [5, 5]], 'difficult': [[6, 2], [6, 3]],
         'name': '灰烬地城 · 门厅规则验收场'}
PROFILES = {
    'warden': {'name': '巡门卫士', 'source': 'Guard melee profile', 'srd_pages': [296],
               'ac': 16, 'max_hp': 11, 'speed': 30, 'initiative_bonus': 1,
               'attack_bonus': 3, 'damage_die': 6, 'damage_bonus': 1, 'damage_type': 'piercing',
               'weapon': 'spear', 'position': [3, 2], 'vulnerabilities': [], 'immunities': []},
    'sentinel': {'name': '灰烬骷髅', 'source': 'Skeleton melee profile', 'srd_pages': [325, 326],
                 'ac': 14, 'max_hp': 13, 'speed': 30, 'initiative_bonus': 3,
                 'attack_bonus': 5, 'damage_die': 6, 'damage_bonus': 3, 'damage_type': 'piercing',
                 'weapon': 'shortsword', 'position': [8, 2], 'vulnerabilities': ['bludgeoning'],
                 'immunities': ['poison']},
}


def combatant(seat: str) -> dict:
    actor = deepcopy(PROFILES[seat])
    actor.update(id=seat, team=seat, hp=actor['max_hp'], conditions=[], temp_hp=0,
                 resistances=[], dead=False, knocked_out=False, death_saves=False,
                 stable=False, death_successes=0, death_failures=0,
                 action=True, reaction=True, dodge=False, disengage=False, movement=0)
    return actor


def initial_state() -> dict:
    return {'ruleset': 'SRD-5.2.1', 'milestone': 'M1-melee-laboratory', 'phase': 'lobby',
            'owners': {}, 'actors': {seat: combatant(seat) for seat in PROFILES},
            'order': [], 'initiative': {}, 'index': 0, 'round': 0, 'turn_id': 0,
            'pending': None, 'window_serial': 0, 'winner': None}
