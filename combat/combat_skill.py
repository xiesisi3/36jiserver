# 战斗技能系统
# 共26个技能函数（17攻击 + 9防御），从单机版移植，字段名英文化

import random
import copy

DEFAULT_SKILL_EFFECT = {
    "triggered": False,
    "damage_mod": 1.0,
    "defense_mod": 1.0,
    "target_shift": 0,
    "target_slot_override": None,
    "multi_targets": [],
    "extra_attacks": [],
    "disable_enemy_skills": False,
    "self_damage": 0,
    "ignore_defense": False,
    "force_double_attack": False,
    "return_half_on_death": False,
}


def _check_skill_name(general, expected_name):
    return general.get("skill_name") == expected_name


def _is_slot_alive(team, slot_idx):
    if slot_idx >= len(team):
        return False
    slot = team[slot_idx]
    return slot and slot.get("兵种名称") and slot.get("数量", 0) > 0


def _troop_contains(team, slot_idx, keyword):
    if slot_idx >= len(team) or not team[slot_idx]:
        return False
    return keyword in team[slot_idx].get("兵种名称", "")


def _find_last_alive(team):
    last = None
    for i in range(len(team) - 1, -1, -1):
        if _is_slot_alive(team, i):
            last = i
            break
    return last


def _find_next_alive(team, start):
    for i in range(start + 1, len(team)):
        if _is_slot_alive(team, i):
            return i
    return None


def _get_alive_slots(team):
    return [i for i, s in enumerate(team) if _is_slot_alive(team, i)]


# ========== 攻击方技能 ==========

def skill_strong_attack(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "强攻"):
        return result
    att_force = general.get("force", 0)
    def_force = defender.get("general", {}).get("force", 0)
    if att_force <= def_force:
        return result
    if random.random() > (att_force * 0.5 / 100.0):
        return result
    result["triggered"] = True
    result["damage_mod"] = 1.0 + (att_force * 0.01)
    return result


def skill_surprise_attack(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "奇袭"):
        return result
    if not _troop_contains(attacker.get("team", []), attack_slot, "骑兵"):
        return result
    cav_aff = general.get("cavalry_phase", 0)
    if random.random() > (cav_aff * 10 / 100.0):
        return result
    result["triggered"] = True
    last_alive = _find_last_alive(defender.get("team", []))
    if last_alive is not None:
        result["target_slot_override"] = last_alive
    result["damage_mod"] = 1.0 + (general.get("force", 0) * 0.01)
    return result


def skill_pierce(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "穿透"):
        return result
    if not _troop_contains(attacker.get("team", []), attack_slot, "弓兵"):
        return result
    bow_aff = general.get("archer_phase", 0)
    if random.random() > (bow_aff * 10 / 100.0):
        return result
    result["triggered"] = True
    force = general.get("force", 0)
    extra_damage_mod = force * 1.5 / 100.0
    alive_slots = _get_alive_slots(defender.get("team", []))
    if len(alive_slots) >= 2:
        # 穿透技能：同时攻击第一个存活槽位（原伤害）和第二个存活槽位（额外伤害加成）
        result["multi_targets"] = [
            {"target_slot": alive_slots[0], "damage_mod": 1.0, "skip_defender_skills": True},
            {"target_slot": alive_slots[1], "damage_mod": extra_damage_mod, "skip_defender_skills": True},
        ]
    return result


def skill_assault(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "突击"):
        return result
    if not _troop_contains(attacker.get("team", []), attack_slot, "骑兵"):
        return result
    cav_aff = general.get("cavalry_phase", 0)
    if random.random() > (cav_aff * 10 / 100.0):
        return result
    result["triggered"] = True
    result["damage_mod"] = 1.0 + (general.get("force", 0) * 0.02)
    return result


def skill_gods(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "军神"):
        return result
    att_force = general.get("force", 0)
    def_force = defender.get("general", {}).get("force", 0)
    if att_force <= def_force:
        return result
    charm = general.get("charisma", 0)
    if random.random() > (charm * 0.5 / 100.0):
        return result
    result["triggered"] = True
    def_team = defender.get("team", [])
    multi = []
    for i in range(len(def_team)):
        if _is_slot_alive(def_team, i):
            multi.append({
                "target_slot": i,
                "damage_mod": 1.0,
                "skip_defender_skills": True,
            })
    result["multi_targets"] = multi
    return result


def skill_fire_attack(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "火袭"):
        return result
    att_intel = general.get("intelligence", 0)
    def_intel = defender.get("general", {}).get("intelligence", 0)
    if att_intel <= def_intel:
        return result
    intel_diff = att_intel - def_intel
    if random.random() > (intel_diff * 1.0 / 100.0):
        return result
    result["triggered"] = True
    result["damage_mod"] = 1.0 + (att_intel * 0.01)
    return result


def skill_overlord(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "霸王"):
        return result
    if not context or not context.get("is_double_attack"):
        return result
    result["triggered"] = True
    total_aff = (general.get("infantry_phase", 0) + general.get("cavalry_phase", 0) +
                 general.get("archer_phase", 0) + general.get("governance_phase", 0))
    damage_mod = 1.0 + (total_aff * 0.08)
    def_team = defender.get("team", [])
    multi = []
    for i in range(len(def_team)):
        if _is_slot_alive(def_team, i):
            multi.append({
                "target_slot": i,
                "damage_mod": damage_mod,
                "skip_defender_skills": True,
            })
    result["multi_targets"] = multi
    return result


def skill_zeal(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "狂热"):
        return result
    if not _troop_contains(attacker.get("team", []), attack_slot, "步兵"):
        return result
    inf_aff = general.get("infantry_phase", 0)
    if random.random() > (inf_aff * 10 / 100.0):
        return result
    result["triggered"] = True
    result["damage_mod"] = 1.0 + (general.get("force", 0) * 0.02)
    return result


def skill_inspire(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "鼓舞"):
        return result
    att_charm = general.get("charisma", 0)
    def_charm = defender.get("general", {}).get("charisma", 0)
    if att_charm <= def_charm:
        return result
    force = general.get("force", 0)
    if random.random() > (force * 0.5 / 100.0):
        return result
    result["triggered"] = True
    result["damage_mod"] = 1.0 + (att_charm * 0.01)
    result["force_double_attack"] = True
    return result


def skill_snipe(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "狙击"):
        return result
    if not _troop_contains(attacker.get("team", []), attack_slot, "弓兵"):
        return result
    bow_aff = general.get("archer_phase", 0)
    if random.random() > (bow_aff * 10 / 100.0):
        return result
    result["triggered"] = True
    result["damage_mod"] = 1.0 + (general.get("force", 0) * 0.02)
    return result


def skill_spear_attack(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "枪阵"):
        return result
    if not _troop_contains(attacker.get("team", []), attack_slot, "步兵"):
        return result
    if not _troop_contains(defender.get("team", []), defend_slot, "骑兵"):
        return result
    result["triggered"] = True
    inf_aff = general.get("infantry_phase", 0)
    result["damage_mod"] = 1.0 + (inf_aff * 0.40)
    return result


def skill_strategist(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "奇将"):
        return result
    if not _troop_contains(attacker.get("team", []), attack_slot, "骑兵"):
        return result
    att_intel = general.get("intelligence", 0)
    def_intel = defender.get("general", {}).get("intelligence", 0)
    if att_intel <= def_intel:
        return result
    if random.random() > (att_intel * 0.5 / 100.0):
        return result
    result["triggered"] = True
    result["ignore_defense"] = True
    cav_aff = general.get("cavalry_phase", 0)
    result["damage_mod"] = 1.0 + (cav_aff * 0.18)
    return result


def skill_warrior(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "武卒"):
        return result
    if not _troop_contains(attacker.get("team", []), attack_slot, "步兵"):
        return result
    inf_aff = general.get("infantry_phase", 0)
    if random.random() > (inf_aff * 10 / 100.0):
        return result
    result["triggered"] = True
    charm = general.get("charisma", 0)
    result["damage_mod"] = 1.0 + (charm * 0.01)
    alive_slots = _get_alive_slots(defender.get("team", []))
    if len(alive_slots) >= 2:
        # 武卒技能：同时攻击第一个存活槽位（原伤害）和第二个存活槽位（80%伤害）
        result["multi_targets"] = [
            {"target_slot": alive_slots[0], "damage_mod": 1.0, "skip_defender_skills": True},
            {"target_slot": alive_slots[1], "damage_mod": 0.8, "skip_defender_skills": True},
        ]
    return result


def skill_melee(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "混战"):
        return result
    if not _troop_contains(attacker.get("team", []), attack_slot, "步兵"):
        return result
    inf_aff = general.get("infantry_phase", 0)
    if random.random() > (inf_aff * 10 / 100.0):
        return result
    result["triggered"] = True
    intel = general.get("intelligence", 0)
    damage_mod = 1.0 + (intel * 0.01)
    alive_slots = _get_alive_slots(defender.get("team", []))
    # 混战技能：第一个存活槽位必定被攻击，其余最多2个槽位随机选择
    multi = [{"target_slot": alive_slots[0], "damage_mod": damage_mod, "skip_defender_skills": True}]
    remaining = [s for s in alive_slots if s != alive_slots[0]]
    for _ in range(2):
        if not remaining:
            break
        target = random.choice(remaining)
        multi.append({"target_slot": target, "damage_mod": damage_mod, "skip_defender_skills": True})
        remaining.remove(target)
    result["multi_targets"] = multi
    return result


def skill_peerless(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "无双"):
        return result
    if not _troop_contains(attacker.get("team", []), attack_slot, "骑兵"):
        return result
    att_charm = general.get("charisma", 0)
    def_charm = defender.get("general", {}).get("charisma", 0)
    if att_charm <= def_charm:
        return result
    force = general.get("force", 0)
    if random.random() > (force * 0.5 / 100.0):
        return result
    result["triggered"] = True
    def_team = defender.get("team", [])
    multi = []
    base_damage_mod = 1.0
    for i in range(len(def_team)):
        if _is_slot_alive(def_team, i):
            multi.append({
                "target_slot": i,
                "damage_mod": base_damage_mod,
                "skip_defender_skills": True,
            })
            base_damage_mod *= 0.8
    result["multi_targets"] = multi
    return result


def skill_thrust(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "突刺"):
        return result
    if not _troop_contains(attacker.get("team", []), attack_slot, "骑兵"):
        return result
    cav_aff = general.get("cavalry_phase", 0)
    if random.random() > (cav_aff * 10 / 100.0):
        return result
    result["triggered"] = True
    result["damage_mod"] = 1.0 + (general.get("force", 0) * 0.01)
    alive_slots = _get_alive_slots(defender.get("team", []))
    if len(alive_slots) >= 2:
        # 突刺技能：同时攻击第一个存活槽位（原伤害）和第二个存活槽位（80%伤害）
        result["multi_targets"] = [
            {"target_slot": alive_slots[0], "damage_mod": 1.0, "skip_defender_skills": True},
            {"target_slot": alive_slots[1], "damage_mod": 0.8, "skip_defender_skills": True},
        ]
    return result


def skill_volley(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "乱射"):
        return result
    if not _troop_contains(attacker.get("team", []), attack_slot, "弓兵"):
        return result
    bow_aff = general.get("archer_phase", 0)
    if random.random() > (bow_aff * 10 / 100.0):
        return result
    result["triggered"] = True
    charm = general.get("charisma", 0)
    damage_mod = 1.0 + (charm * 0.01)
    alive_slots = _get_alive_slots(defender.get("team", []))
    # 乱射技能：第一个存活槽位必定被攻击，其余最多2个槽位随机选择
    multi = [{"target_slot": alive_slots[0], "damage_mod": damage_mod, "skip_defender_skills": True}]
    remaining = [s for s in alive_slots if s != alive_slots[0]]
    for _ in range(2):
        if not remaining:
            break
        target = random.choice(remaining)
        multi.append({"target_slot": target, "damage_mod": damage_mod, "skip_defender_skills": True})
        remaining.remove(target)
    result["multi_targets"] = multi
    return result


def skill_god_attack(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "神将"):
        return result
    att_force = general.get("force", 0)
    def_force = defender.get("general", {}).get("force", 0)
    if att_force <= def_force:
        return result
    intel = general.get("intelligence", 0)
    if random.random() > (intel * 0.5 / 100.0):
        return result
    result["triggered"] = True
    charm = general.get("charisma", 0)
    result["damage_mod"] = 1.0 + (charm * 0.01)
    return result


def skill_prophet_attack(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = attacker.get("general", {})
    if not _check_skill_name(general, "神算"):
        return result
    att_intel = general.get("intelligence", 0)
    def_intel = defender.get("general", {}).get("intelligence", 0)
    if att_intel <= def_intel:
        return result
    if random.random() > (att_intel * 0.5 / 100.0):
        return result
    result["triggered"] = True
    force = general.get("force", 0)
    damage_mod = 1.0 + (force * 0.02)
    def_team = defender.get("team", [])
    multi = []
    for i in range(len(def_team)):
        if _is_slot_alive(def_team, i):
            multi.append({
                "target_slot": i,
                "damage_mod": damage_mod,
                "skip_defender_skills": True,
            })
    result["multi_targets"] = multi
    return result


# ========== 防御方技能 ==========

def skill_counterattack(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    if context and context.get("is_counter"):
        return result
    general = defender.get("general", {})
    if not _check_skill_name(general, "反击"):
        return result
    def_team = defender.get("team", [])
    att_team = attacker.get("team", [])
    if not _is_slot_alive(def_team, defend_slot):
        return result
    if not _is_slot_alive(att_team, attack_slot):
        return result
    def_count = def_team[defend_slot].get("数量", 0)
    att_count = att_team[attack_slot].get("数量", 0)
    if def_count <= att_count:
        return result
    intel = general.get("intelligence", 0)
    if random.random() > (intel * 0.5 / 100.0):
        return result
    result["triggered"] = True
    result["extra_attacks"] = [{
        "attacker": defender,
        "defender": attacker,
        "attack_slot": defend_slot,
        "defend_slot": attack_slot,
        "context": {"is_counter": True},
        "damage_mod": 1.0,
        "skip_defender_skills": False,
    }]
    return result


def skill_beauty(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    if context and context.get("is_counter"):
        return result
    general = defender.get("general", {})
    if not _check_skill_name(general, "倾城"):
        return result
    charm = general.get("charisma", 0)
    if random.random() > (charm * 0.5 / 100.0):
        return result
    result["triggered"] = True
    intel = general.get("intelligence", 0)
    damage_mod = intel * 0.5 / 100.0
    result["extra_attacks"] = [{
        "attacker": defender,
        "defender": attacker,
        "attack_slot": defend_slot,
        "defend_slot": attack_slot,
        "context": {"is_counter": True},
        "damage_mod": damage_mod,
        "skip_defender_skills": False,
    }]
    return result


def skill_charm(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = defender.get("general", {})
    if not _check_skill_name(general, "魅惑"):
        return result
    def_charm = general.get("charisma", 0)
    att_charm = attacker.get("general", {}).get("charisma", 0)
    if def_charm <= att_charm:
        return result
    intel = general.get("intelligence", 0)
    if random.random() > (intel * 0.5 / 100.0):
        return result
    result["triggered"] = True
    result["damage_mod"] = 0.0
    return result


def skill_defend(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = defender.get("general", {})
    if not _check_skill_name(general, "固守"):
        return result
    intel = general.get("intelligence", 0)
    if random.random() > (intel * 1.0 / 100.0):
        return result
    result["triggered"] = True
    result["defense_mod"] = 1.0 + (intel * 0.01)
    return result


def skill_prophet_defend(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = defender.get("general", {})
    if not _check_skill_name(general, "神算"):
        return result
    def_intel = general.get("intelligence", 0)
    att_intel = attacker.get("general", {}).get("intelligence", 0)
    if def_intel <= att_intel:
        return result
    result["triggered"] = True
    result["disable_enemy_skills"] = True
    return result


def skill_spear_defend(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = defender.get("general", {})
    if not _check_skill_name(general, "枪阵"):
        return result
    if not _troop_contains(defender.get("team", []), defend_slot, "步兵"):
        return result
    if not _troop_contains(attacker.get("team", []), attack_slot, "骑兵"):
        return result
    result["triggered"] = True
    inf_aff = general.get("infantry_phase", 0)
    result["defense_mod"] = 1.0 + (inf_aff * 0.20)
    return result


def skill_suicide(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = defender.get("general", {})
    if not _check_skill_name(general, "陷阵"):
        return result
    def_team = defender.get("team", [])
    if not _is_slot_alive(def_team, defend_slot):
        return result
    if not _troop_contains(def_team, defend_slot, "步兵"):
        return result
    inf_aff = general.get("infantry_phase", 0)
    if random.random() > (inf_aff * 8 / 100.0):
        return result
    result["triggered"] = True
    intel = general.get("intelligence", 0)
    damage = int(intel * 0.5 / 100 * def_team[defend_slot].get("数量", 0))
    result["self_damage"] = damage
    return result


def skill_god_defend(attacker, defender, attack_slot, defend_slot, context=None):
    result = DEFAULT_SKILL_EFFECT.copy()
    general = defender.get("general", {})
    if not _check_skill_name(general, "神将"):
        return result
    def_force = general.get("force", 0)
    att_force = attacker.get("general", {}).get("force", 0)
    if def_force <= att_force:
        return result
    intel = general.get("intelligence", 0)
    if random.random() > (intel * 0.5 / 100.0):
        return result
    result["triggered"] = True
    result["return_half_on_death"] = True
    return result


SKILL_FUNCTIONS = {
    "强攻": skill_strong_attack,
    "奇袭": skill_surprise_attack,
    "穿透": skill_pierce,
    "突击": skill_assault,
    "军神": skill_gods,
    "火袭": skill_fire_attack,
    "霸王": skill_overlord,
    "狂热": skill_zeal,
    "鼓舞": skill_inspire,
    "狙击": skill_snipe,
    "枪阵-攻击": skill_spear_attack,
    "奇将": skill_strategist,
    "武卒": skill_warrior,
    "混战": skill_melee,
    "无双": skill_peerless,
    "突刺": skill_thrust,
    "乱射": skill_volley,
    "神将-攻击": skill_god_attack,
    "神算-攻击": skill_prophet_attack,
    "反击": skill_counterattack,
    "倾城": skill_beauty,
    "魅惑": skill_charm,
    "固守": skill_defend,
    "神算-防御": skill_prophet_defend,
    "枪阵-防御": skill_spear_defend,
    "陷阵": skill_suicide,
    "神将-防御": skill_god_defend,
}


def _get_skill_key(skill_name, role):
    if skill_name in ("神算", "枪阵", "神将"):
        return f"{skill_name}-{role}"
    return skill_name


def get_attacker_skill_effect(attacker, defender, attack_slot, context):
    general = attacker.get("general", {})
    skill_name = general.get("skill_name")
    if not skill_name or skill_name == "无":
        return DEFAULT_SKILL_EFFECT.copy()
    skill_key = _get_skill_key(skill_name, "攻击")
    skill_func = SKILL_FUNCTIONS.get(skill_key)
    if skill_func is None:
        return DEFAULT_SKILL_EFFECT.copy()
    return skill_func(attacker, defender, attack_slot, None, context)


def get_defender_skill_effect(attacker, defender, attack_slot, defend_slot, context):
    general = defender.get("general", {})
    skill_name = general.get("skill_name")
    if not skill_name or skill_name == "无":
        return DEFAULT_SKILL_EFFECT.copy()
    skill_key = _get_skill_key(skill_name, "防御")
    skill_func = SKILL_FUNCTIONS.get(skill_key)
    if skill_func is None:
        return DEFAULT_SKILL_EFFECT.copy()
    return skill_func(attacker, defender, attack_slot, defend_slot, context)