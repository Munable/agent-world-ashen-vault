"""Audited fixed G2 player builds. This is world content, not a generic character builder."""
from copy import deepcopy
from .content import combatant

CLASS_KEYS = ("fighter", "rogue", "wizard")

FIGHTER_BUILD = {
    "ruleset": "SRD 5.2.1", "class_key": "fighter", "class": "Fighter", "species": "Halfling",
    "background": "原创守路人（SRD 背景创建规则）",
    "abilities": {"str":17,"dex":13,"con":15,"int":10,"wis":12,"cha":8},
    "ability_source": "标准数组 15/13/14/10/12/8；背景 Str+2、Con+1",
    "background_abilities": ["str","dex","con"], "origin_feat": "Skilled", "style": "defense",
    "saves": {"str":5,"dex":1,"con":4,"int":0,"wis":1,"cha":-1},
    "skills": {"athletics":5,"perception":3,"medicine":3,"intimidation":1,"stealth":3,"survival":3,"insight":3},
    "skill_sources": {"background":["athletics","perception"],"skilled":["medicine","intimidation","stealth"],"fighter":["survival","insight"]},
    "tool": "carpenters_tools", "languages": ["common","dwarvish","elvish"],
    "masteries": ["flail","morningstar","mace"], "supported_weapons": ["flail","morningstar","mace"],
    "equipment_budget": {"fighter_gp":155,"fighter_spent_gp":127,"background_gp":50,"background_spent_gp":10,"remaining_gp":68},
    "equipment": ["chain_mail","shield","flail","morningstar","mace","dungeoneers_pack","carpenters_tools","travelers_clothes"],
    "starting_potion_source": "营地委托方提供一瓶，不计入 SRD 初始装备预算",
}

ROGUE_BUILD = {
    "ruleset": "SRD 5.2.1", "class_key": "rogue", "class": "Rogue", "species": "Halfling",
    "background": "原创墓库斥候（SRD 背景创建规则）",
    "abilities": {"str":8,"dex":17,"con":15,"int":13,"wis":12,"cha":10},
    "ability_source": "标准数组 15/14/13/12/10/8；背景 Dex+2、Con+1",
    "background_abilities": ["dex","con","int"], "origin_feat": "Skilled",
    "saves": {"str":-1,"dex":5,"con":2,"int":3,"wis":1,"cha":0},
    "skills": {"athletics":-1,"perception":3,"medicine":1,"intimidation":2,"stealth":7,
               "investigation":3,"sleight_of_hand":5,"acrobatics":5,"insight":1},
    "skill_sources": {"rogue":["acrobatics","investigation","perception","stealth"],"expertise":["stealth","perception"],
                     "skilled":["intimidation","sleight_of_hand","medicine"]},
    "tool": "thieves_tools", "languages": ["common","dwarvish","thieves_cant","elvish"],
    "masteries": ["shortsword","shortbow"], "supported_weapons": ["shortsword"],
    "equipment": ["leather_armor","shortsword","shortbow","arrows_20","thieves_tools","burglars_pack","travelers_clothes"],
    "campaign_purse_source": "本序章统一远征金 68 GP；不冒充 Rogue 初始装备余款",
    "starting_potion_source": "营地委托方提供一瓶",
}

WIZARD_BUILD = {
    "ruleset": "SRD 5.2.1", "class_key": "wizard", "class": "Wizard", "species": "Halfling",
    "background": "原创灰烬抄录员（SRD 背景创建规则）",
    "abilities": {"str":8,"dex":14,"con":15,"int":17,"wis":12,"cha":10},
    "ability_source": "标准数组 15/14/13/12/10/8；背景 Int+2、Con+1",
    "background_abilities": ["int","con","wis"], "origin_feat": "Skilled",
    "saves": {"str":-1,"dex":2,"con":2,"int":5,"wis":3,"cha":0},
    "skills": {"athletics":-1,"perception":1,"medicine":3,"intimidation":0,"stealth":2,
               "arcana":5,"history":5,"investigation":5,"insight":3},
    "skill_sources": {"wizard":["arcana","history"],"skilled":["investigation","insight","medicine"]},
    "tool": "calligraphers_tools", "languages": ["common","dwarvish","elvish"],
    "masteries": [], "supported_weapons": ["quarterstaff"],
    "equipment": ["dagger","dagger","arcane_focus_quarterstaff","robe","spellbook","scholars_pack","travelers_clothes"],
    "cantrips": ["light","mage_hand","ray_of_frost"],
    "spellbook": ["detect_magic","feather_fall","mage_armor","magic_missile","sleep","thunderwave"],
    "prepared": ["mage_armor","magic_missile"],
    "implemented_spells": ["mage_armor","magic_missile","ray_of_frost"],
    "campaign_purse_source": "本序章统一远征金 68 GP；不冒充 Wizard 初始装备余款",
    "starting_potion_source": "营地委托方提供一瓶",
}

BUILDS = {"fighter": FIGHTER_BUILD, "rogue": ROGUE_BUILD, "wizard": WIZARD_BUILD}


def build_for(class_key: str) -> dict:
    if class_key not in BUILDS:
        raise ValueError("UnsupportedClass")
    return deepcopy(BUILDS[class_key])


def hero_for(class_key: str) -> dict:
    build = build_for(class_key)
    hero = combatant("warden")
    common = dict(
        id="hero", name={"fighter":"守路旅人","rogue":"墓库斥候","wizard":"灰烬抄录员"}[class_key],
        team="hero", size="small", nimble=True, lucky=True, brave=True, naturally_stealthy=True,
        death_saves=True, bonus_action=True, extra_actions=0, class_key=class_key,
    )
    if class_key == "fighter":
        hero.update(source="Audited Fighter 1-3 build", srd_pages=[23,47,48,86,87,90,91,92,95,185,187,192,193],
                    ac=19,max_hp=12,hp=12,attack_bonus=5,damage_die=8,damage_bonus=3,damage_type="bludgeoning",
                    weapon="flail",mastery="sap",initiative_bonus=1,critical_threshold=20,remarkable_athlete=False,**common)
    elif class_key == "rogue":
        hero.update(source="Audited Rogue 1-3 build", ac=14,max_hp=10,hp=10,attack_bonus=5,damage_die=6,
                    damage_bonus=3,damage_type="piercing",weapon="shortsword",mastery="vex",weapon_finesse=True,
                    initiative_bonus=3,sneak_attack_dice=1,**common)
    else:
        hero.update(source="Audited Wizard 1-3 build", ac=12,max_hp=8,hp=8,attack_bonus=1,damage_die=6,
                    damage_bonus=-1,damage_type="bludgeoning",weapon="quarterstaff",mastery=None,
                    initiative_bonus=2,spell_attack_bonus=5,spell_save_dc=13,unarmored_ac=12,**common)
    return hero


def hp_gain(class_key: str) -> int:
    # Fixed-value HP option plus Constitution +2 for all three audited builds.
    return {"fighter": 8, "rogue": 7, "wizard": 6}[class_key]


def spell_slot_capacity(level: int) -> dict[str, int]:
    if level <= 0:
        return {"1": 0, "2": 0}
    if level == 1:
        return {"1": 2, "2": 0}
    if level == 2:
        return {"1": 3, "2": 0}
    return {"1": 4, "2": 2}

SPELLS = {
    "mage_armor": {"level": 1, "components": ["v", "s", "m"], "material_focus": True, "concentration": False},
    "magic_missile": {"level": 1, "components": ["v", "s"], "concentration": False},
    "shield": {"level": 1, "components": ["v", "s"], "concentration": False, "reaction": True},
    "ray_of_frost": {"level": 0, "components": ["v", "s"], "concentration": False},
    "blur": {"level": 2, "components": ["v"], "concentration": True},
    "scorching_ray": {"level": 2, "components": ["v", "s"], "concentration": False},
}

def prepared_capacity(level: int) -> int:
    return {1: 4, 2: 5, 3: 6}.get(level, 6)

