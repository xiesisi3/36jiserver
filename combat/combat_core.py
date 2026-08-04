# 战斗核心引擎
# 回合制战斗编排器 + 攻击计算 + 快照生成

import math
import copy
import random
import logging

from data.troop_data import TROOP_DATA, TROOP_DATA_SPECIAL
from combat.combat_constants import (
    TECH_BONUS, DEFENSE_HERO_BONUS, HP_HERO_BONUS,
)
from combat.combat_utils import (
    get_troop_attack, get_troop_defense, get_troop_hp, get_troop_series,
    get_troop_food_cost, get_counter_bonus,
    find_target_position, get_phase_for_series, get_double_attack_rate,
    is_team_eliminated,
    get_tech_attack_multiplier, get_tech_combo_bonus,
)
from combat.combat_skill import (
    DEFAULT_SKILL_EFFECT,
    get_attacker_skill_effect,
    get_defender_skill_effect,
)
from general.general_core import TALENT_BONUSES
from server_timer.server_timer_core import get_uptime_ms

logger = logging.getLogger('36ji-server')


def _is_slot_alive(team, slot_idx):
    if slot_idx >= len(team):
        return False
    slot = team[slot_idx]
    return slot and slot.get("兵种名称") and slot.get("数量", 0) > 0


def _merge_effects(e1, e2):
    merged = {
        "triggered": e1.get("triggered", False) or e2.get("triggered", False),
        "damage_mod": e1.get("damage_mod", 1.0) * e2.get("damage_mod", 1.0),
        "defense_mod": e1.get("defense_mod", 1.0) * e2.get("defense_mod", 1.0),
        "target_shift": e1.get("target_shift", 0) + e2.get("target_shift", 0),
        "target_slot_override": e2.get("target_slot_override") or e1.get("target_slot_override"),
        "multi_targets": e1.get("multi_targets", []) + e2.get("multi_targets", []),
        "extra_attacks": e1.get("extra_attacks", []) + e2.get("extra_attacks", []),
        "disable_enemy_skills": e1.get("disable_enemy_skills", False) or e2.get("disable_enemy_skills", False),
        "self_damage": e1.get("self_damage", 0) + e2.get("self_damage", 0),
        "ignore_defense": e1.get("ignore_defense", False) or e2.get("ignore_defense", False),
        "force_double_attack": e1.get("force_double_attack", False) or e2.get("force_double_attack", False),
        "return_half_on_death": e1.get("return_half_on_death", False) or e2.get("return_half_on_death", False),
    }
    return merged


def _prepare_attack_stats(attacker, att_slot, defender, def_slot):
    attacker_team = attacker["team"]
    attacker_slot = attacker_team[att_slot]
    attacker_troop_name = attacker_slot.get("兵种名称", "")
    attacker_count = attacker_slot.get("数量", 0)

    defender_team = defender["team"]
    defender_slot = defender_team[def_slot]
    defender_troop_name = defender_slot.get("兵种名称", "")

    attack_power = get_troop_attack(attacker_troop_name) * get_tech_attack_multiplier(attacker.get("user_id", ""), attacker_troop_name)
    defense = get_troop_defense(defender_troop_name)

    town_defense_attack_bonus = attacker.get("_town_defense_attack_bonus", 0)
    if town_defense_attack_bonus:
        attack_power *= (1 + town_defense_attack_bonus)

    town_defense_defense_bonus = defender.get("_town_defense_defense_bonus", 0)
    if town_defense_defense_bonus:
        defense *= (1 + town_defense_defense_bonus)

    hp = get_troop_hp(defender_troop_name)

    attacker_general = attacker["general"]
    att_force = attacker_general.get("force", 0)
    att_intel = attacker_general.get("intelligence", 0)
    hero_bonus = 1 + att_force * 0.005 + att_intel * 0.0025

    attacker_series = get_troop_series(attacker_troop_name)
    defender_series = get_troop_series(defender_troop_name)
    counter_bonus = get_counter_bonus(attacker_series, defender_series)

    defender_general = defender["general"]
    phase_value = get_phase_for_series(defender_general, defender_series)
    phase_bonus = 1 + phase_value * 0.05

    talent_tqtb_level = defender_general.get("talent_tqtb", 0)
    defense += TALENT_BONUSES.get("铜墙铁壁", {}).get(talent_tqtb_level, 0)

    # 武将加成类道具（buff）：攻击/防御/血量倍率，无加成时默认0.0不影响原公式
    attack_bonus = attacker_general.get("attack_bonus", 0.0)
    attack_power *= (1 + attack_bonus)

    defense_bonus = defender_general.get("defense_bonus", 0.0)
    defense *= (1 + defense_bonus)

    hp_bonus = defender_general.get("hp_bonus", 0.0)
    hp *= (1 + hp_bonus)

    return (attack_power, defense, attacker_count, hero_bonus, counter_bonus,
            TECH_BONUS, hp, phase_bonus, DEFENSE_HERO_BONUS, HP_HERO_BONUS)


def _compute_damage_and_apply(attacker, att_slot, defender, def_slot, effect):
    """计算伤害并应用到防御方，返回 (killed, exp_gained, damage_value)"""
    defender_team = defender["team"]
    defender_slot = defender_team[def_slot]
    defender_count = defender_slot.get("数量", 0)

    if defender_count <= 0:
        return 0, 0, 0

    (attack_power, defense, attacker_count,
     hero_bonus, counter_bonus, tech_bonus,
     hp, phase_bonus, def_bonus, hp_bonus) = _prepare_attack_stats(
         attacker, att_slot, defender, def_slot
    )

    ignore_def = effect.get("ignore_defense", False)
    if ignore_def:
        defense = 0
        def_bonus = 1
        phase_bonus = 1

    damage_mod = effect.get("damage_mod", 1.0)
    def_mod = effect.get("defense_mod", 1.0)

    numerator = max(0, (attack_power - defense)) * counter_bonus * tech_bonus * hero_bonus * attacker_count
    numerator = int(numerator * damage_mod)

    denominator = hp * phase_bonus * def_bonus * hp_bonus * def_mod

    if denominator <= 0:
        damage = 0
    else:
        damage = math.floor(numerator / denominator)

    killed = min(damage, defender_count)

    killed = max(0, killed)
    defender_slot["数量"] -= killed

    defender_troop_name = defender_slot.get("兵种名称", "")

    if defender_slot["数量"] <= 0:
        defender_slot["兵种名称"] = ""
        defender_slot["数量"] = 0

    exp_gained = 0
    if killed > 0 and defender_troop_name:
        for troop in TROOP_DATA:
            if troop["兵种名称"] == defender_troop_name:
                exp_gained = int(troop.get("gain_exp", 0) * killed)
                break
        if exp_gained == 0:
            for troop in TROOP_DATA_SPECIAL:
                if troop["兵种名称"] == defender_troop_name:
                    exp_gained = int(troop.get("gain_exp", 0) * killed)
                    break

    consumed_units = attacker_count
    if killed == defender_count and denominator > 0:
        base = max(1, (attack_power - defense)) * counter_bonus * tech_bonus * hero_bonus
        if base > 0:
            min_units = math.ceil(defender_count * denominator / (base * damage_mod))
            consumed_units = min(min_units, attacker_count)

    attacker_slot_data = attacker["team"][att_slot]
    attacker_troop_name = attacker_slot_data.get("兵种名称", "")
    food_cost_per_unit = get_troop_food_cost(attacker_troop_name)
    food_consumed = consumed_units * food_cost_per_unit
    attacker["food"] = max(0, attacker.get("food", 0) - food_consumed)

    return killed, exp_gained, numerator


def _process_single_attack(attacker, defender, att_slot, context, total_killed_out, total_exp_out, triggered_skills_out, target_kills_out=None, double_attack_kills_out=None, double_attack_triggered_skills_out=None, counter_target_kills_out=None, da_counter_target_kills_out=None):
    """处理一个槽位的单次攻击（含技能、连击、额外攻击），不返回步骤，直接累加结果
    target_kills_out: 可选列表，记录技能多目标的 (目标槽位, 击杀数)
    double_attack_kills_out: 可选列表，记录连击的 (目标槽位, 击杀数)（独立攻击频次）
    double_attack_triggered_skills_out: 可选列表，记录连击触发的技能名
    counter_target_kills_out: 可选列表，记录防御方反击的 (目标槽位, 击杀数)
    da_counter_target_kills_out: 可选列表，记录连击中防御方反击的 (目标槽位, 击杀数)
    """
    if not _is_slot_alive(attacker["team"], att_slot):
        return

    attacker_slot = attacker["team"][att_slot]
    attacker_troop_name = attacker_slot.get("兵种名称", "")
    attacker_count = attacker_slot.get("数量", 0)

    if get_troop_attack(attacker_troop_name) == 0:
        return

    food_cost_per_unit = get_troop_food_cost(attacker_troop_name)
    required_food = attacker_count * food_cost_per_unit
    if attacker.get("food", 0) < required_food:
        return

    att_general = attacker.get("general", {})
    att_skill_name = att_general.get("skill_name", "")

    if context.get("disable_enemy_skills"):
        att_effect = copy.deepcopy(DEFAULT_SKILL_EFFECT)
    else:
        att_effect = get_attacker_skill_effect(attacker, defender, att_slot, context)

    def_team = defender["team"]
    base_target = find_target_position(def_team)
    if base_target == -1:
        return

    target_slot = att_effect.get("target_slot_override")
    if target_slot is None:
        target_slot = base_target
    if target_slot < 0 or target_slot >= len(def_team) or not _is_slot_alive(def_team, target_slot):
        target_slot = base_target

    original_slot_info = None
    if target_slot < len(def_team):
        slot = def_team[target_slot]
        if slot:
            original_slot_info = {
                "name": slot.get("兵种名称", ""),
                "count": slot.get("数量", 0),
            }

    if att_effect.get("disable_enemy_skills"):
        def_effect = copy.deepcopy(DEFAULT_SKILL_EFFECT)
    else:
        def_effect = get_defender_skill_effect(attacker, defender, att_slot, target_slot, context)

    final_effect = _merge_effects(att_effect, def_effect)

    if att_effect.get("triggered") and att_skill_name and att_skill_name != "无":
        triggered_skills_out.append(att_skill_name)
    else:
        triggered_skills_out.append(None)

    def_skill_name = defender.get("general", {}).get("skill_name", "")
    if def_effect.get("triggered") and def_skill_name and def_skill_name != "无":
        triggered_skills_out.append(def_skill_name)
    else:
        triggered_skills_out.append(None)

    multi_targets = final_effect.get("multi_targets", [])
    if not multi_targets:
        multi_targets = [{
            "target_slot": target_slot,
            "damage_mod": final_effect.get("damage_mod", 1.0),
            "skip_defender_skills": False,
        }]

    for tgt in multi_targets:
        tgt_slot = tgt["target_slot"]
        if tgt_slot >= len(def_team) or not _is_slot_alive(def_team, tgt_slot):
            continue
        effect_for_target = copy.deepcopy(final_effect)
        effect_for_target["damage_mod"] = final_effect.get("damage_mod", 1.0) * tgt.get("damage_mod", 1.0)
        killed, exp_gained, _ = _compute_damage_and_apply(
            attacker, att_slot, defender, tgt_slot, effect_for_target
        )
        total_killed_out[0] += killed
        total_exp_out[0] += exp_gained
        if target_kills_out is not None:
            target_kills_out.append((tgt_slot, killed))

    if final_effect.get("self_damage", 0) > 0:
        self_dmg = final_effect["self_damage"]
        att_team = attacker["team"]
        if att_slot < len(att_team) and att_team[att_slot]:
            att_team[att_slot]["数量"] = max(0, att_team[att_slot].get("数量", 0) - self_dmg)

    if def_effect.get("return_half_on_death") and original_slot_info:
        current_slot = def_team[target_slot] if target_slot < len(def_team) else None
        current_count = current_slot.get("数量", 0) if current_slot else 0
        if current_count == 0 and original_slot_info["count"] > 0:
            returned = original_slot_info["count"] // 2
            if returned > 0:
                if current_slot is None:
                    while len(def_team) <= target_slot:
                        def_team.append({"兵种名称": "", "数量": 0})
                    current_slot = def_team[target_slot]
                current_slot["兵种名称"] = original_slot_info["name"]
                current_slot["数量"] = returned

    for extra in def_effect.get("extra_attacks", []):
        if extra.get("context", {}).get("is_counter") and context.get("is_counter"):
            continue
        new_context = context.copy()
        new_context.update(extra.get("context", {}))
        _process_single_attack(
            extra["attacker"], extra["defender"],
            extra["attack_slot"],
            context=new_context,
            total_killed_out=total_killed_out,
            total_exp_out=total_exp_out,
            triggered_skills_out=triggered_skills_out,
            target_kills_out=counter_target_kills_out,
            double_attack_triggered_skills_out=double_attack_triggered_skills_out,
            da_counter_target_kills_out=da_counter_target_kills_out,
        )

    for extra in att_effect.get("extra_attacks", []):
        new_context = context.copy()
        new_context.update(extra.get("context", {}))
        _process_single_attack(
            extra["attacker"], extra["defender"],
            extra["attack_slot"],
            context=new_context,
            total_killed_out=total_killed_out,
            total_exp_out=total_exp_out,
            triggered_skills_out=triggered_skills_out,
            target_kills_out=target_kills_out,
            double_attack_triggered_skills_out=double_attack_triggered_skills_out,
            da_counter_target_kills_out=da_counter_target_kills_out,
        )

    if not context.get("is_double_attack"):
        double_attack = False
        if att_effect.get("force_double_attack"):
            double_attack = True
        else:
            # 连击率计算：优先使用未过期的士气加成（buff），过期或无加成时使用基础士气
            current_uptime = get_uptime_ms()
            morale_bonus = att_general.get("morale_bonus", 0.0)
            morale_bonus_expire = att_general.get("morale_bonus_expire") or 0
            if current_uptime < morale_bonus_expire and morale_bonus > 0:
                effective_morale = morale_bonus
            else:
                effective_morale = att_general.get("morale", 0)
            rate = get_double_attack_rate(effective_morale)
            combo_rate = att_general.get("combo_rate", 0)
            # 霸王技能额外增加12%连击率
            if att_general.get("skill_name") == "霸王":
                combo_rate += 0.12
            rate += combo_rate * 100
            rate += get_tech_combo_bonus(attacker.get("user_id", ""), attacker_troop_name) * 100
            if random.random() < rate / 100.0:
                double_attack = True

        if double_attack:
            next_target = find_target_position(def_team)
            if next_target == -1:
                next_target = target_slot
            new_context = context.copy()
            new_context["is_double_attack"] = True
            _process_single_attack(
                attacker, defender, att_slot,
                context=new_context,
                total_killed_out=total_killed_out,
                total_exp_out=total_exp_out,
                triggered_skills_out=double_attack_triggered_skills_out,
                target_kills_out=double_attack_kills_out,
                counter_target_kills_out=da_counter_target_kills_out,
            )


def _get_initial_snapshot(troop):
    team_names = [s.get("兵种名称", "") if s else "" for s in troop["team"]]
    team_counts = [s.get("数量", 0) if s else 0 for s in troop["team"]]
    return {
        "ti": troop["troop_id"],
        "gn": troop["general"].get("hero_name", ""),
        "gid": troop["general"].get("id", 0),
        "t": team_names,
        "c": team_counts,
        "f": troop["food"],
    }


def run_robber_battle(player_troop, enemy_troop):
    """执行剿匪战斗（1回合，先手方+后手方各行动一次）

    :param player_troop: 玩家部队
    :param enemy_troop: 敌方部队
    :return: 战斗快照字典
    """
    player_intel = player_troop["general"].get("intelligence", 0)
    enemy_intel = enemy_troop["general"].get("intelligence", 0)

    logger.info(f"[战斗] 开始剿匪战斗 玩家智力={player_intel} 敌方智力={enemy_intel} "
                f"玩家兵力={[s.get('数量',0) if s else 0 for s in player_troop['team']]} "
                f"玩家粮食={player_troop['food']} "
                f"敌方兵力={[s.get('数量',0) if s else 0 for s in enemy_troop['team']]} "
                f"敌方粮食={enemy_troop['food']}")

    if player_intel >= enemy_intel:
        first = player_troop
        second = enemy_troop
    else:
        first = enemy_troop
        second = player_troop

    init_data = {
        "L": [_get_initial_snapshot(player_troop)],
        "R": [_get_initial_snapshot(enemy_troop)],
    }

    rounds = []
    total_exp = 0

    for attacker in [first, second]:
        if attacker["troop_id"] > 0:
            defender = enemy_troop
        else:
            defender = player_troop

        def_initial_counts = [s.get("数量", 0) if s and s.get("兵种名称") else 0 for s in defender["team"]]

        atk_list = []
        for slot_idx in range(5):
            if not _is_slot_alive(attacker["team"], slot_idx):
                atk_list.append({"s": slot_idx, "t": None, "k": 0, "f": attacker["food"]})
                continue

            attacker_slot = attacker["team"][slot_idx]
            attacker_troop_name = attacker_slot.get("兵种名称", "")
            attacker_count = attacker_slot.get("数量", 0)

            if get_troop_attack(attacker_troop_name) == 0:
                atk_list.append({"s": slot_idx, "t": None, "k": 0, "f": attacker["food"]})
                continue

            food_cost_per_unit = get_troop_food_cost(attacker_troop_name)
            required_food = attacker_count * food_cost_per_unit
            if attacker.get("food", 0) < required_food:
                atk_list.append({"s": slot_idx, "t": None, "k": 0, "f": attacker["food"]})
                continue

            base_target = find_target_position(defender["team"])
            if base_target == -1:
                atk_list.append({"s": slot_idx, "t": None, "k": 0, "f": attacker["food"]})
                continue

            total_killed = [0]
            slot_exp = [0]
            triggered_skills = []
            target_kills = []
            double_attack_kills = []
            double_attack_triggered = []
            counter_kills = []
            da_counter_kills = []

            _process_single_attack(
                attacker, defender, slot_idx,
                context={},
                total_killed_out=total_killed,
                total_exp_out=slot_exp,
                triggered_skills_out=triggered_skills,
                target_kills_out=target_kills,
                double_attack_kills_out=double_attack_kills,
                double_attack_triggered_skills_out=double_attack_triggered,
                counter_target_kills_out=counter_kills,
                da_counter_target_kills_out=da_counter_kills,
            )

            total_exp += slot_exp[0]

            if target_kills:
                first_t = target_kills[0][0]
                first_k = target_kills[0][1]
                entry = {
                    "s": slot_idx,
                    "t": first_t,
                    "k": first_k,
                    "f": attacker["food"],
                }
                if len(target_kills) > 1:
                    entry["mt"] = [{"t": t, "k": k} for t, k in target_kills[1:]]
            else:
                entry = {
                    "s": slot_idx,
                    "t": None,
                    "k": 0,
                    "f": attacker["food"],
                }
            if double_attack_kills:
                da_first = double_attack_kills[0]
                da_entry = {"t": da_first[0], "k": da_first[1]}
                if len(double_attack_kills) > 1:
                    da_entry["mt"] = [{"t": t, "k": k} for t, k in double_attack_kills[1:]]
                if double_attack_triggered[0]:
                    da_entry["sk"] = double_attack_triggered[0]
                if double_attack_triggered[1]:
                    da_entry["dk"] = double_attack_triggered[1]
                if da_counter_kills:
                    da_entry["ct"] = [{"t": t, "k": k} for t, k in da_counter_kills]
                entry["da"] = da_entry
            if triggered_skills[0]:
                entry["sk"] = triggered_skills[0]
            if triggered_skills[1]:
                entry["dk"] = triggered_skills[1]
            if counter_kills:
                entry["ct"] = [{"t": t, "k": k} for t, k in counter_kills]
            atk_list.append(entry)

        def_delta = []
        for i in range(5):
            before = def_initial_counts[i] if i < len(def_initial_counts) else 0
            current = defender["team"][i].get("数量", 0) if i < len(defender["team"]) and defender["team"][i] else 0
            def_delta.append(max(0, before - current))

        rounds.append({
            "a": attacker["troop_id"],
            "atk": atk_list,
            "dr": {"dc": def_delta},
        })

    player_team = player_troop["team"]
    enemy_team = enemy_troop["team"]

    player_eliminated = is_team_eliminated(player_team)
    enemy_eliminated = is_team_eliminated(enemy_team)

    if player_eliminated:
        win = -1
    elif enemy_eliminated:
        win = 0
    else:
        win = 1

    result = {
        "w": win,
        "e": total_exp,
        "tf": player_troop["food"],
        "tc": [s.get("数量", 0) if s else 0 for s in player_team],
        "ef": enemy_troop["food"],
        "ec": [s.get("数量", 0) if s else 0 for s in enemy_team],
    }

    return {
        "init": init_data,
        "rounds": rounds,
        "result": result,
        "total_exp": total_exp,
        "player_troop": player_troop,
        "enemy_troop": enemy_troop,
    }