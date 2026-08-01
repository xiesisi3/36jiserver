import copy
import logging
import random

from server_timer.server_timer_core import get_uptime_ms
from data.global_data import towns_cache, troop_cache, fight_round_vars, user_nation_cache
from towns.towns_outer.town_outer_grid_core import _calculate_gate_positions
from towns.towns_outer.town_outer_combat.combat_move import (
    GRID_ROWS, GRID_COLS, DIRECTIONS, is_valid_cell,
    get_troop_owner, is_enemy, is_troop_alive,
    get_troop_move_range, get_attack_range,
    find_best_target_with_path, manhattan_distance,
    calculate_round_duration, calculate_troop_timing,
    count_sub_actions,
    _bfs_full_range, _get_flanking_positions, _find_fallback_target, _reconstruct_path,
    execute_flanking_movement,
)
from general.general_utils import get_general_info
from combat.combat_core import (
    _process_single_attack, _is_slot_alive,
)
from combat.combat_utils import (
    get_troop_attack, get_troop_food_cost, find_target_position,
    is_team_eliminated, recalc_troop_food,
)
from general.general_core import TALENT_BONUSES

logger = logging.getLogger("36ji-server")


def _make_troop_state(troop, include_general=False):
    """
    生成部队的客户端展示状态（精简版），用于发送给客户端渲染战斗画面。
    include_general=True时包含武将信息（武力、智力、魅力等）。
    """
    user_id = str(troop.get("user_id", "")) if troop.get("user_id") is not None else ""
    st = {
        "p": list(troop.get("grid_pos", [])),
        "t": [],
        "uid": user_id,
        "n": user_nation_cache.get(user_id, 0),
        "f": troop.get("food", 0),
    }
    team = troop.get("team", [])
    for slot in team:
        if slot and slot.get("兵种名称"):
            st["t"].append([slot["兵种名称"], slot.get("数量", 0)])
        else:
            st["t"].append(["", 0])
    if include_general:
        g = troop.get("general", {})
        if g:
            st["g"] = {
                "hn": g.get("hero_name", ""),
                "lv": g.get("level", 0),
                "fo": g.get("force", 0),
                "it": g.get("intelligence", 0),
                "ch": g.get("charisma", 0),
            }
    return st


def _has_attack_capability(sim):
    """判断部队是否有攻击能力（至少有一个槽位的兵种攻击力 > 0）"""
    team = sim.get("team", [])
    for slot in team:
        if slot and get_troop_attack(slot.get("兵种名称", "")) > 0:
            return True
    return False


def _make_all_states(troops_map, include_general=False):
    """生成所有部队的客户端展示状态，用于战斗回合开始时保存初始状态快照"""
    return {tid: _make_troop_state(t, include_general) for tid, t in troops_map.items()}


def _build_attack_list(sim, target_sim):
    """构建攻击列表：遍历攻击方的5个槽位，对每个存活且可攻击的槽位执行一次攻击流程"""
    atk_list = []
    for slot_idx in range(5):
        if not _is_slot_alive(sim["team"], slot_idx):
            continue

        attacker_slot = sim["team"][slot_idx]
        attacker_troop_name = attacker_slot.get("兵种名称", "")
        attacker_count = attacker_slot.get("数量", 0)

        if get_troop_attack(attacker_troop_name) == 0:
            continue

        food_cost_per_unit = get_troop_food_cost(attacker_troop_name)
        required_food = attacker_count * food_cost_per_unit
        if sim.get("food", 0) < required_food:
            continue

        base_target = find_target_position(target_sim["team"])
        if base_target == -1:
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
            sim, target_sim, slot_idx,
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

        if target_kills:
            first_t = target_kills[0][0]
            first_k = target_kills[0][1]
            entry = {
                "s": slot_idx,
                "t": first_t,
                "k": first_k,
                "f": sim.get("food", 0),
            }
            if len(target_kills) > 1:
                entry["mt"] = [{"t": t, "k": k} for t, k in target_kills[1:]]
        else:
            entry = {
                "s": slot_idx,
                "t": None,
                "k": 0,
                "f": sim.get("food", 0),
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

    return atk_list


COUNTER_SKILLS = {"反击", "倾城"}


def _get_troop_general_id(sim):
    return sim.get("general_id")


def _compute_general_kills_from_attack_list(
    attacker_troop, target_troop,
    atk_list,
    general_kills,
    eliminated_troops=None,
    target_team_names=None,
    attacker_team_names=None,
):
    attacker_general_id = _get_troop_general_id(attacker_troop)
    target_general_id = _get_troop_general_id(target_troop)
    attacker_user_id = str(attacker_troop.get("user_id", ""))
    target_user_id = str(target_troop.get("user_id", ""))
    attacker_tid = attacker_troop.get("troop_id")
    target_tid = target_troop.get("troop_id")

    def _troop_name(team, slot_idx, snap=None):
        if snap is not None:
            if slot_idx is None or slot_idx < 0 or slot_idx >= len(snap):
                return None
            return snap[slot_idx] or None
        if slot_idx is None or slot_idx < 0:
            return None
        if slot_idx >= len(team):
            return None
        slot = team[slot_idx]
        return slot.get("兵种名称", "") if slot else ""

    target_team = target_troop.get("team", [])
    attacker_team = attacker_troop.get("team", [])

    def _add_kills(general_id, user_id, troop_name, count):
        if not general_id or not troop_name or count <= 0:
            return
        if user_id == "0":
            return
        key = (general_id, user_id)
        gk = general_kills.setdefault(key, {"kills": {}, "losses": {}})
        gk["kills"][troop_name] = gk["kills"].get(troop_name, 0) + count

    def _add_losses(general_id, user_id, troop_name, count):
        if not general_id or not troop_name or count <= 0:
            return
        if user_id == "0":
            return
        key = (general_id, user_id)
        gk = general_kills.setdefault(key, {"kills": {}, "losses": {}})
        gk["losses"][troop_name] = gk["losses"].get(troop_name, 0) + count

    def _add_eliminated(general_id, user_id, eliminated_tid):
        if eliminated_troops is None:
            return
        if user_id == "0":
            return
        key = (general_id, user_id)
        if key not in eliminated_troops:
            eliminated_troops[key] = set()
        eliminated_troops[key].add(eliminated_tid)

    for entry in (atk_list or []):
        t = entry.get("t")
        k = entry.get("k", 0)
        if t is not None and k > 0:
            name = _troop_name(target_team, t, snap=target_team_names)
            _add_kills(attacker_general_id, attacker_user_id, name, k)
            _add_losses(target_general_id, target_user_id, name, k)

        for mt_entry in entry.get("mt", []):
            mt_t = mt_entry.get("t")
            mt_k = mt_entry.get("k", 0)
            if mt_t is not None and mt_k > 0:
                name = _troop_name(target_team, mt_t, snap=target_team_names)
                _add_kills(attacker_general_id, attacker_user_id, name, mt_k)
                _add_losses(target_general_id, target_user_id, name, mt_k)

        da = entry.get("da")
        if da:
            da_t = da.get("t")
            da_k = da.get("k", 0)
            if da_t is not None and da_k > 0:
                name = _troop_name(target_team, da_t, snap=target_team_names)
                _add_kills(attacker_general_id, attacker_user_id, name, da_k)
                _add_losses(target_general_id, target_user_id, name, da_k)

            for da_mt_entry in da.get("mt", []):
                da_mt_t = da_mt_entry.get("t")
                da_mt_k = da_mt_entry.get("k", 0)
                if da_mt_t is not None and da_mt_k > 0:
                    name = _troop_name(target_team, da_mt_t, snap=target_team_names)
                    _add_kills(attacker_general_id, attacker_user_id, name, da_mt_k)
                    _add_losses(target_general_id, target_user_id, name, da_mt_k)

            da_dk = da.get("dk")
            if da_dk in COUNTER_SKILLS:
                for da_ct_entry in da.get("ct", []):
                    da_ct_t = da_ct_entry.get("t")
                    da_ct_k = da_ct_entry.get("k", 0)
                    if da_ct_t is not None and da_ct_k > 0:
                        name = _troop_name(attacker_team, da_ct_t, snap=attacker_team_names)
                        _add_kills(target_general_id, target_user_id, name, da_ct_k)
                        _add_losses(attacker_general_id, attacker_user_id, name, da_ct_k)

        dk = entry.get("dk")
        if dk in COUNTER_SKILLS:
            for ct_entry in entry.get("ct", []):
                ct_t = ct_entry.get("t")
                ct_k = ct_entry.get("k", 0)
                if ct_t is not None and ct_k > 0:
                    name = _troop_name(attacker_team, ct_t, snap=attacker_team_names)
                    _add_kills(target_general_id, target_user_id, name, ct_k)
                    _add_losses(attacker_general_id, attacker_user_id, name, ct_k)

    # 追踪消灭的部队：攻击方消灭目标 → 记录目标部队ID
    if is_team_eliminated(target_troop.get("team", [])):
        _add_eliminated(attacker_general_id, attacker_user_id, target_tid)
    # 反击消灭攻击方 → 记录攻击方部队ID
    if is_team_eliminated(attacker_troop.get("team", [])):
        _add_eliminated(target_general_id, target_user_id, attacker_tid)


def _build_round_data(sim_troops):
    return {
        "troops": {
            str(tid): {
                "grid_pos": list(sim.get("grid_pos", [])),
                "team": [
                    {
                        "兵种名称": slot.get("兵种名称", "") if slot else "",
                        "数量": slot.get("数量", 0) if slot else 0,
                    }
                    for slot in (sim.get("team") or [])
                ],
                "food": sim.get("food", 0),
            }
            for tid, sim in sim_troops.items()
        }
    }


def _compute_round_stats(id_to_dynamic, sim_troops, state_snapshots, user_nation_cache):
    troop_user = {}
    troop_owner = {}
    for tid, troop in id_to_dynamic.items():
        uid = str(troop.get("user_id", ""))
        troop_user[tid] = uid
        troop_owner[tid] = user_nation_cache.get(uid, 0)

    def count_soldiers(team):
        return sum(slot.get("数量", 0) for slot in (team or []) if slot and slot.get("兵种名称"))

    attacked_troops = set()
    for entry in state_snapshots:
        tid = entry["id"]
        atk_list = entry.get("atk") or []
        for atk in atk_list:
            if atk.get("t") is not None:
                attacked_troops.add(tid)
                break

    def init_stat():
        return {"troops": 0, "non_attack": 0, "dead": 0, "total_forces": 0, "killed": 0, "lost": 0}

    player_stats = {}
    owner_stats = {}

    for tid, troop in id_to_dynamic.items():
        uid = troop_user[tid]
        owner = troop_owner[tid]

        ps = player_stats.setdefault(uid, init_stat())
        os = owner_stats.setdefault(owner, init_stat())

        initial_soldiers = count_soldiers(troop.get("team", []))
        sim = sim_troops.get(tid)
        final_soldiers = count_soldiers(sim.get("team", [])) if sim else 0
        alive_start = is_troop_alive(troop)
        alive_end = is_troop_alive(sim) if sim else False

        ps["troops"] += 1
        ps["total_forces"] += initial_soldiers
        ps["lost"] += initial_soldiers - final_soldiers
        os["troops"] += 1
        os["total_forces"] += initial_soldiers
        os["lost"] += initial_soldiers - final_soldiers

        if tid not in attacked_troops:
            ps["non_attack"] += 1
            os["non_attack"] += 1
        if alive_start and not alive_end:
            ps["dead"] += 1
            os["dead"] += 1

    for entry in state_snapshots:
        attacker_id = entry["id"]
        target_id = entry.get("tg")
        attacker_uid = troop_user.get(attacker_id)
        attacker_owner = troop_owner.get(attacker_id)
        target_uid = troop_user.get(target_id) if target_id else None
        target_owner = troop_owner.get(target_id) if target_id else None

        atk_list = entry.get("atk") or []
        for atk in atk_list:
            k = atk.get("k", 0)
            mt = atk.get("mt", [])
            total_kills = k + sum(m.get("k", 0) for m in mt)

            if total_kills > 0:
                if attacker_uid and attacker_uid in player_stats:
                    player_stats[attacker_uid]["killed"] += total_kills
                if attacker_owner is not None and attacker_owner in owner_stats:
                    owner_stats[attacker_owner]["killed"] += total_kills

            da = atk.get("da")
            if da:
                da_k = da.get("k", 0)
                da_mt = da.get("mt", [])
                da_total = da_k + sum(m.get("k", 0) for m in da_mt)
                if da_total > 0:
                    if attacker_uid and attacker_uid in player_stats:
                        player_stats[attacker_uid]["killed"] += da_total
                    if attacker_owner is not None and attacker_owner in owner_stats:
                        owner_stats[attacker_owner]["killed"] += da_total

            ct = atk.get("ct")
            if ct:
                ct_total = sum(c.get("k", 0) for c in ct)
                if ct_total > 0:
                    if target_uid and target_uid in player_stats:
                        player_stats[target_uid]["killed"] += ct_total
                    if target_owner is not None and target_owner in owner_stats:
                        owner_stats[target_owner]["killed"] += ct_total

    return {"players": player_stats, "owners": owner_stats}


def process_round_logic(town_id, battle_troops, round_num):
    """
    战斗回合主逻辑入口。
    按智力从高到低排序部队行动顺序，每支部队：
    1. 根据target_type选择目标（策略A：最近 / 策略B：最高攻击等）
    2. BFS计算移动路径，移动到目标附近
    3. 包围移动（随机选择目标周围的攻击位）
    4. 执行攻击（_build_attack_list）
    5. 额外行动（霸王/武卒/无双技能 + 一鼓作气天赋）
    返回 (troop_order, id_to_dynamic, general_kills, eliminated_troops, round_data)
    """
    preload_start_ms = fight_round_vars[town_id]["preload_start_ms"] if town_id in fight_round_vars else get_uptime_ms()
    round_start_ms = get_uptime_ms()

    for troop in battle_troops:
        if not troop.get("general"):
            general = get_general_info(troop.get("general_id"))
            troop["general"] = general if general else {}

    def troop_key(t):
        general = t.get("general", {})
        intel = general.get("intelligence", 20)
        create_time = t.get("create_time", 0)
        return (-intel, create_time)

    troop_order = sorted(battle_troops, key=troop_key)
    troop_order_ids = [t["troop_id"] for t in troop_order]

    gate_positions = _calculate_gate_positions(town_id)
    unmovable_set = set(gate_positions) if gate_positions else set()
    unmovable_set.add((9, 9))

    id_to_dynamic = {}
    for t in troop_order:
        id_to_dynamic[t["troop_id"]] = copy.deepcopy(t)

    initial_state = _make_all_states(id_to_dynamic, include_general=True)

    troop_paths = {}
    troop_targets = {}
    attack_sequences = {}
    state_snapshots = []
    sim_troops = {tid: copy.deepcopy(t) for tid, t in id_to_dynamic.items()}
    general_kills = {}
    eliminated_troops = {}

    for idx, troop in enumerate(troop_order):
        tid = troop["troop_id"]
        sim = sim_troops.get(tid)
        if not sim or not is_troop_alive(sim):
            as_entry = {
                "id": tid,
                "ph": [],
                "tg": None,
                "atk": None,
            }
            state_snapshots.append(as_entry)
            troop_paths[tid] = []
            troop_targets[tid] = None
            continue

        current_pos = sim.get("grid_pos")
        start_pos = tuple(current_pos) if current_pos else None
        path = [start_pos] if start_pos else []

        move_range = get_troop_move_range(sim)
        attack_range = get_attack_range(sim)

        if not start_pos:
            as_entry = {
                "id": tid,
                "ph": [[p[0], p[1]] for p in path],
                "tg": None,
                "atk": None,
            }
            state_snapshots.append(as_entry)
            troop_paths[tid] = path
            troop_targets[tid] = None
            continue

        steps_left = move_range
        current = start_pos
        target_id = None
        target_type = sim.get("target_type", "nearest")

        while steps_left > 0:
            target_pos, bfs_path, bfs_dist, target_troop = find_best_target_with_path(
                sim, list(sim_troops.values()), unmovable_set, user_nation_cache, target_type
            )

            if target_pos is None:
                break

            if bfs_dist <= attack_range:
                target_id = target_troop.get("troop_id") if target_troop else None
                # 包围移动：目标已在攻击范围内，尝试从目标周围随机选一个攻击位
                # 这样即使多个部队攻击同一目标，也能分散站位，避免挤在一起
                if steps_left > 0:
                    new_current, flanking_path, steps_left = execute_flanking_movement(
                        current, sim, target_troop, attack_range, move_range,
                        steps_left, unmovable_set, sim_troops, user_nation_cache
                    )
                    current = new_current
                    path.extend(flanking_path)
                break

            if bfs_path and len(bfs_path) > 0:
                next_step = bfs_path[0]
                enemy_positions_set = {
                    tuple(t.get("grid_pos", [])) for t in sim_troops.values()
                    if is_enemy(sim, t, user_nation_cache) and is_troop_alive(t) and t.get("grid_pos")
                }
                if next_step not in enemy_positions_set or next_step == current:
                    if next_step not in enemy_positions_set:
                        current = next_step
                        path.append(current)
                        sim["grid_pos"] = list(current)
                        steps_left -= 1
                else:
                    break
            else:
                break

        if target_id is None:
            final_target_pos, final_bfs_path, final_bfs_dist, final_target_troop = find_best_target_with_path(
                sim, list(sim_troops.values()), unmovable_set, user_nation_cache, target_type
            )
            if final_target_pos is not None and final_bfs_dist <= attack_range:
                target_id = final_target_troop.get("troop_id") if final_target_troop else None

        troop_paths[tid] = path
        troop_targets[tid] = target_id

        # 保底攻击：移动后若原目标不在攻击范围内，在攻击范围内寻找可攻击的敌军
        if target_id is not None:
            ts = sim_troops.get(target_id)
            if ts and ts.get("grid_pos"):
                target_pos = tuple(ts["grid_pos"])
                if manhattan_distance(current, target_pos) > attack_range:
                    atk_dist_map, _ = _bfs_full_range(current, unmovable_set, attack_range)
                    fallback = _find_fallback_target(
                        sim, list(sim_troops.values()), attack_range, atk_dist_map, target_type, user_nation_cache
                    )
                    if fallback is not None:
                        target_id = fallback.get("troop_id")
                        troop_targets[tid] = target_id

        # 如果部队所有槽位均为非攻击兵种，跳过攻击
        if not _has_attack_capability(sim):
            target_id = None
        target_sim = sim_troops.get(target_id) if target_id else None

        as_entry = {
            "id": tid,
            "ph": [[p[0], p[1]] for p in path],
            "tg": target_id,
            "atk": None,
        }

        if target_sim and is_troop_alive(target_sim) and is_enemy(sim, target_sim, user_nation_cache):
            target_team_names = [slot.get("兵种名称", "") if slot else "" for slot in target_sim.get("team", [])]
            attacker_team_names = [slot.get("兵种名称", "") if slot else "" for slot in sim.get("team", [])]
            atk_list = _build_attack_list(sim, target_sim)
            as_entry["atk"] = atk_list
            _compute_general_kills_from_attack_list(
                sim, target_sim,
                atk_list,
                general_kills,
                eliminated_troops=eliminated_troops,
                target_team_names=target_team_names,
                attacker_team_names=attacker_team_names,
            )

        attack_sequences[tid] = as_entry["atk"]
        state_snapshots.append(as_entry)

        skill_name = troop["general"].get("skill_name", "")
        extra_act_count = 0
        talent_ygzq_level = troop["general"].get("talent_ygzq", 0)
        talent_ygzq_bonus = TALENT_BONUSES.get("一鼓作气", {}).get(talent_ygzq_level, 0)
        has_skill = skill_name in ("霸王", "武卒", "无双")
        if has_skill:
            max_extra_acts = 1 + talent_ygzq_bonus
        else:
            max_extra_acts = talent_ygzq_bonus

        current_target_sim = target_sim

        while extra_act_count < max_extra_acts and (has_skill or talent_ygzq_bonus > 0):
            if not current_target_sim or not is_team_eliminated(current_target_sim["team"]):
                break

            if not is_troop_alive(sim):
                break

            extra_act_count += 1

            current_pos = sim.get("grid_pos")
            if not current_pos:
                break

            move_range = get_troop_move_range(sim)
            attack_range = get_attack_range(sim)

            steps_left = move_range
            current = tuple(current_pos)
            new_path = [current]
            new_target_id = None

            while steps_left > 0:
                target_pos, bfs_path, bfs_dist, target_troop = find_best_target_with_path(
                    sim, list(sim_troops.values()), unmovable_set, user_nation_cache, target_type
                )

                if target_pos is None:
                    break

                if bfs_dist <= attack_range:
                    new_target_id = target_troop.get("troop_id") if target_troop else None
                    # 包围移动：额外行动同样需要包围逻辑
                    if steps_left > 0:
                        new_current, flanking_path, steps_left = execute_flanking_movement(
                            current, sim, target_troop, attack_range, move_range,
                            steps_left, unmovable_set, sim_troops, user_nation_cache
                        )
                        current = new_current
                        new_path.extend(flanking_path)
                    break

                if bfs_path and len(bfs_path) > 0:
                    next_step = bfs_path[0]
                    enemy_positions_set = {
                        tuple(t.get("grid_pos", [])) for t in sim_troops.values()
                        if is_enemy(sim, t, user_nation_cache) and is_troop_alive(t) and t.get("grid_pos")
                    }
                    if next_step not in enemy_positions_set or next_step == current:
                        if next_step not in enemy_positions_set:
                            current = next_step
                            new_path.append(current)
                            sim["grid_pos"] = list(current)
                            steps_left -= 1
                    else:
                        break
                else:
                    break

            if new_target_id is None:
                final_target_pos, final_bfs_path, final_bfs_dist, final_target_troop = find_best_target_with_path(
                    sim, list(sim_troops.values()), unmovable_set, user_nation_cache, target_type
                )
                if final_target_pos is not None and final_bfs_dist <= attack_range:
                    new_target_id = final_target_troop.get("troop_id") if final_target_troop else None

            new_target_sim = sim_troops.get(new_target_id) if new_target_id else None

            as_entry = {
                "id": tid,
                "ph": [[p[0], p[1]] for p in new_path],
                "tg": new_target_id,
                "atk": None,
            }

            if new_target_sim and is_troop_alive(new_target_sim) and is_enemy(sim, new_target_sim, user_nation_cache):
                target_team_names = [slot.get("兵种名称", "") if slot else "" for slot in new_target_sim.get("team", [])]
                attacker_team_names = [slot.get("兵种名称", "") if slot else "" for slot in sim.get("team", [])]
                atk_list = _build_attack_list(sim, new_target_sim)
                as_entry["atk"] = atk_list
                _compute_general_kills_from_attack_list(
                    sim, new_target_sim,
                    atk_list,
                    general_kills,
                    eliminated_troops=eliminated_troops,
                    target_team_names=target_team_names,
                    attacker_team_names=attacker_team_names,
                )

            attack_sequences[tid] = as_entry["atk"]
            state_snapshots.append(as_entry)
            current_target_sim = new_target_sim

    stats = _compute_round_stats(id_to_dynamic, sim_troops, state_snapshots, user_nation_cache)

    round_data = _build_round_data(sim_troops)

    for tid, sim in sim_troops.items():
        if tid in id_to_dynamic:
            # 裁剪粮食上限（部队损兵后粮食上限可能下降，超出部分丢弃）
            recalc_troop_food(sim)
            id_to_dynamic[tid]["grid_pos"] = list(sim["grid_pos"]) if sim.get("grid_pos") else id_to_dynamic[tid].get("grid_pos")
            id_to_dynamic[tid]["team"] = copy.deepcopy(sim["team"])
            id_to_dynamic[tid]["food"] = sim.get("food", 0)

    tm = calculate_troop_timing(state_snapshots)
    total_duration_ms = tm[-1]["e"] if tm else 0
    estimated_end_time = round_start_ms + int(total_duration_ms * 1.01)

    previous_frv = fight_round_vars.get(town_id, {})
    fight_round_vars[town_id] = {
        "round_num": round_num,
        "is_active": True,
        "start_time": round_start_ms,
        "estimated_end_time": estimated_end_time,
        "total_duration_ms": total_duration_ms,
        "preload_start_ms": preload_start_ms,
        "history_id": previous_frv.get("history_id"),
        "troop_order": troop_order_ids,
        "troop_paths": troop_paths,
        "troop_targets": troop_targets,
        "attack_sequences": attack_sequences,
        "current_index": -1,
        "calc_completed": True,
        "waiting_until": None,
        "stats": stats,
        "log": [],
        "tm": tm,
        "ss": state_snapshots,
        "is": initial_state,
        "_battle_troops": previous_frv.get("_battle_troops", []),
        "_defenders": previous_frv.get("_defenders", []),
        "_arriving": previous_frv.get("_arriving", []),
    }

    return troop_order, id_to_dynamic, general_kills, eliminated_troops, round_data


def get_round_dynamic_troops(town_id):
    frv = fight_round_vars.get(town_id)
    if not frv:
        return {}
    return frv.get("_dynamic_troops", {})


def set_round_dynamic_troops(town_id, dynamic_troops):
    if town_id in fight_round_vars:
        fight_round_vars[town_id]["_dynamic_troops"] = dynamic_troops