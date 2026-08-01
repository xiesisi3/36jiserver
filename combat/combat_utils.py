# 战斗工具函数

import copy
import random

from data.troop_data import TROOP_DATA
from combat.combat_constants import (
    COUNTER_BONUS, MORALE_TO_DOUBLE_ATTACK_RATE,
    ROBBER_DIFFICULTY_CONFIG,
)
from data.tech_data import SERIES_TO_ATTACK_TECH, SERIES_TO_COMBO_TECH
from data.global_data import tech_cache


def get_troop_attack(troop_name):
    for t in TROOP_DATA:
        if t["兵种名称"] == troop_name:
            return t.get("攻击力", 0)
    return 0


def get_troop_defense(troop_name):
    for t in TROOP_DATA:
        if t["兵种名称"] == troop_name:
            return t.get("防御力", 0)
    return 0


def get_troop_hp(troop_name):
    for t in TROOP_DATA:
        if t["兵种名称"] == troop_name:
            return t.get("生命值", 0)
    return 0


def get_troop_series(troop_name):
    for t in TROOP_DATA:
        if t["兵种名称"] == troop_name:
            return t.get("兵种系列", "")
    return ""


def get_tech_attack_multiplier(user_id, troop_name):
    """获取科技攻击力加成倍率（含武刚军阵/胡服骑射/风林火山）"""
    series = get_troop_series(troop_name)
    tech_type = SERIES_TO_ATTACK_TECH.get(series)
    if not tech_type:
        return 1.0
    user_techs = tech_cache.get(user_id, {})
    level = user_techs.get(tech_type, 0)
    return 1.0 + level * 0.05


def get_tech_combo_bonus(user_id, troop_name):
    """获取科技连击率加成（步兵协战/弓兵协战/骑兵协战）"""
    series = get_troop_series(troop_name)
    tech_type = SERIES_TO_COMBO_TECH.get(series)
    if not tech_type:
        return 0.0
    user_techs = tech_cache.get(user_id, {})
    level = user_techs.get(tech_type, 0)
    return level * 0.01


def get_troop_food_cost(troop_name):
    for t in TROOP_DATA:
        if t["兵种名称"] == troop_name:
            return t.get("攻击消耗粮食", 0)
    return 0


def get_troop_carry_food(troop_name):
    for t in TROOP_DATA:
        if t["兵种名称"] == troop_name:
            return t.get("可携带粮食", 0)
    return 0


def get_troop_gain_exp(troop_name):
    for t in TROOP_DATA:
        if t["兵种名称"] == troop_name:
            return t.get("gain_exp", 0)
    return 0


def get_counter_bonus(attacker_series, defender_series):
    return COUNTER_BONUS.get((attacker_series, defender_series), 1.0)


def find_target_position(team):
    for i, slot in enumerate(team):
        if not slot:
            continue
        if slot.get("兵种名称") and slot.get("数量", 0) > 0:
            return i
    return -1


def calc_round_food_cost(troop_data):
    total_cost = 0
    team = troop_data.get("team", [])
    for slot in team:
        if not slot:
            continue
        troop_name = slot.get("兵种名称", "")
        if not troop_name:
            continue
        if get_troop_attack(troop_name) == 0:
            continue
        count = slot.get("数量", 0)
        total_cost += count * get_troop_food_cost(troop_name)
    return total_cost


def recalc_troop_food(troop_data):
    new_max_food = 0
    team = troop_data.get("team", [])
    for slot in team:
        if not slot:
            continue
        troop_name = slot.get("兵种名称", "")
        if not troop_name:
            continue
        count = slot.get("数量", 0)
        new_max_food += count * get_troop_carry_food(troop_name)
    current_food = troop_data.get("food", 0)
    if current_food > new_max_food:
        troop_data["food"] = new_max_food
    troop_data["max_food"] = new_max_food
    return new_max_food


def get_double_attack_rate(morale):
    rate = 0
    for threshold, r in MORALE_TO_DOUBLE_ATTACK_RATE:
        if morale >= threshold:
            rate = r
        else:
            break
    return min(rate, 100)


def generate_enemy_troop(difficulty):
    cfg = ROBBER_DIFFICULTY_CONFIG.get(difficulty)
    if cfg is None:
        cfg = ROBBER_DIFFICULTY_CONFIG["极易"]

    team = copy.deepcopy(cfg["team"])

    general = {
        "id": -1,
        "hero_name": cfg["general_name"],
        "force": cfg["force"],
        "intelligence": cfg["intelligence"],
        "charisma": cfg["charisma"],
        "level": 1,
        "skill_name": "",
        "skill_desc": "",
        "infantry_phase": 0,
        "cavalry_phase": 0,
        "archer_phase": 0,
        "governance_phase": 0,
        "morale": 100,
        "wisdom": 0,
        "personality": "",
        "exp_bonus": 0.0,
        "attack_bonus": 0.0,
        "defense_bonus": 0.0,
        "hp_bonus": 0.0,
        "morale_bonus": 0.0,
    }

    return {
        "troop_id": -1,
        "general": general,
        "team": team,
        "food": cfg["food"],
        "exp_mult": cfg["exp_mult"],
    }


def build_combat_troop(troop_id, troop_data, general_data, user_id=""):
    return {
        "troop_id": troop_id,
        "user_id": user_id,
        "general": dict(general_data),
        "team": copy.deepcopy(troop_data["team"]),
        "food": troop_data.get("food", 0),
        "exp_mult": 1.0,
    }


def get_phase_for_series(general, series):
    phase_map = {
        "步兵系": "infantry_phase",
        "骑兵系": "cavalry_phase",
        "弓兵系": "archer_phase",
    }
    field = phase_map.get(series, "infantry_phase")
    return general.get(field, 0)


def count_alive_slots(team):
    return sum(1 for s in team if s and s.get("兵种名称") and s.get("数量", 0) > 0)


def is_team_eliminated(team):
    return count_alive_slots(team) == 0