import asyncio
import logging
import copy

from server_timer.server_timer_core import get_uptime_ms
from data.global_data import (
    towns_cache, troop_cache, fight_round_vars,
    troops_arrived_at_town, user_nation_cache,
)
from towns.towns_outer.town_outer_combat.combat_prepare import (
    enter_battle_preparation, check_combat_end, finish_combat,
    _assign_gate_positions, PRELOAD_DURATION_MS,
    _get_and_clear_arriving_troops,
)
from towns.towns_outer.town_outer_combat.combat_round import (
    process_round_logic,
)
from towns.towns_outer.town_outer_combat.combat_move import (
    is_troop_alive,
)
from towns.towns_outer.town_outer_combat.combat_db import (
    insert_combat_round, update_combat_round, get_combat_round_by_history,
    insert_general_kills, update_combat_history,
)
from towns.towns_db import update_town_status
from troop.troop_db import update_troop, delete_troop
from core.connection import broadcast
from message.protocol import make_response
from combat.combat_utils import recalc_troop_food
from general.general_utils import get_general_info
from general.general_db import update_general
from general.general_core import add_exp, sync_cache_update
from data.troop_data import TROOP_DATA, TROOP_DATA_SPECIAL

logger = logging.getLogger("36ji-server")


def _get_own_troops_from_grid(town_id):
    grid_data = fight_round_vars.get(town_id)
    if not grid_data:
        logger.warning(f"[战斗] _get_own_troops_from_grid 城池{town_id}: fight_round_vars 中无数据")
        return []
    troops = grid_data.get("_battle_troops", [])
    result = [copy.deepcopy(t) for t in troops if is_troop_alive(t)]
    return result


def _collect_newly_arrived_troops(town_id, preload_start_ms, preload_end_ms):
    newly_arrived = []
    arrived_ids = troops_arrived_at_town.get(town_id, [])
    for tid in list(arrived_ids):
        troop = troop_cache.get(tid)
        if not troop:
            arrived_ids.remove(tid)
            continue
        arrive_time = troop.get("arrive_time", 0) or 0
        if preload_start_ms <= arrive_time <= preload_end_ms and is_troop_alive(troop):
            troop_copy = copy.deepcopy(troop)
            troop_copy["troop_id"] = tid
            gx = troop_copy.get("grid_x")
            gy = troop_copy.get("grid_y")
            troop_copy["grid_pos"] = [gx, gy] if gx is not None and gy is not None else None
            newly_arrived.append(troop_copy)
            arrived_ids.remove(tid)
    return newly_arrived


async def _start_round(town_id, round_num, battle_troops):
    preload_start_ms = fight_round_vars.get(town_id, {}).get("preload_start_ms", 0)
    preload_end_ms = get_uptime_ms()

    for troop in battle_troops:
        tid = troop["troop_id"]
        if tid in troop_cache and troop_cache[tid].get("status") != 3:
            troop_cache[tid]["status"] = 3
            troop_cache[tid]["pos"] = town_id
            troop_cache[tid]["dest"] = None
            await update_troop(tid, {"status": 3, "pos": town_id, "dest": None})

    towns_cache[town_id]["status"] = 2
    await update_town_status(town_id, 2)

    # 记录回合开始时的部队初始兵力，用于战斗结算统计
    initial_troops = {}
    for troop in battle_troops:
        total = 0
        for slot in (troop.get("team") or []):
            if slot and slot.get("兵种名称"):
                total += slot.get("数量", 0)
        initial_troops[troop["troop_id"]] = {
            "s": total,
            "u": troop.get("user_id", ""),
        }

    troop_order, id_to_dynamic, general_kills, eliminated_troops, round_data, morale_updates = process_round_logic(town_id, battle_troops, round_num)

    # 每回合结束后持久化：粮食裁剪、死亡部队删除、存活部队写入DB
    frv = fight_round_vars.get(town_id, {})
    now_ms = get_uptime_ms()
    dead_ids = set()
    for troop in battle_troops:
        tid = troop["troop_id"]
        dyn = id_to_dynamic.get(tid)
        if not dyn:
            continue
        # 裁剪粮食上限（部队损兵后粮食上限可能下降，超出部分丢弃）
        recalc_troop_food(dyn)
        troop["team"] = copy.deepcopy(dyn["team"])
        troop["food"] = dyn.get("food", 0)
        troop["grid_pos"] = list(dyn["grid_pos"]) if dyn.get("grid_pos") else None
        if not is_troop_alive(troop):
            # 部队死亡：从DB删除、从缓存移除
            dead_ids.add(tid)
            await delete_troop(tid)
            if tid in troop_cache:
                del troop_cache[tid]
            # 记录玩家武将死亡（山贼武将不记录）
            user_id = str(troop.get("user_id", ""))
            general_id = troop.get("general_id")
            if user_id != "0" and general_id:
                general = get_general_info(general_id)
                if general:
                    # 武将阵亡：重置士气为100，清空所有加成道具效果及过期时间
                    general["status"] = 4
                    general["death_time"] = now_ms
                    general["pos"] = None
                    general["dest"] = None
                    general["morale"] = 100
                    general["attack_bonus"] = 0.0
                    general["defense_bonus"] = 0.0
                    general["hp_bonus"] = 0.0
                    general["exp_bonus"] = 0.0
                    general["morale_bonus"] = 0.0
                    general["attack_bonus_expire"] = None
                    general["defense_bonus_expire"] = None
                    general["hp_bonus_expire"] = None
                    general["exp_bonus_expire"] = None
                    general["morale_bonus_expire"] = None
                    await update_general(general_id, {
                        "status": 4, "death_time": now_ms,
                        "pos": None, "dest": None,
                        "morale": 100,
                        "attack_bonus": 0.0, "defense_bonus": 0.0,
                        "hp_bonus": 0.0, "exp_bonus": 0.0, "morale_bonus": 0.0,
                        "attack_bonus_expire": None, "defense_bonus_expire": None,
                        "hp_bonus_expire": None, "exp_bonus_expire": None,
                        "morale_bonus_expire": None,
                    })
        else:
            # 部队存活：更新DB和缓存
            if tid in troop_cache:
                troop_cache[tid]["team"] = copy.deepcopy(dyn["team"])
                troop_cache[tid]["food"] = dyn.get("food", 0)
                troop_cache[tid]["grid_pos"] = list(dyn["grid_pos"]) if dyn.get("grid_pos") else None
            await update_troop(tid, {
                "team": copy.deepcopy(dyn["team"]),
                "food": dyn.get("food", 0),
                "grid_x": dyn["grid_pos"][0] if dyn.get("grid_pos") else None,
                "grid_y": dyn["grid_pos"][1] if dyn.get("grid_pos") else None,
            })
    # 从 _battle_troops 中移除死亡部队，仅保留存活部队
    if dead_ids:
        frv["_battle_troops"] = [t for t in battle_troops if t["troop_id"] not in dead_ids]
    round_start_ms = frv.get("start_time", get_uptime_ms())
    round_end_ms = frv.get("estimated_end_time", get_uptime_ms())
    history_id = frv.get("history_id")

    existing = await get_combat_round_by_history(history_id, round_num)
    if existing:
        await update_combat_round(history_id, round_num, {
            "state": 1,
            "preload_start_ms": preload_start_ms,
            "preload_end_ms": preload_end_ms,
            "round_start_ms": round_start_ms,
            "round_end_ms": round_end_ms,
            "round_data": round_data,
            "initial_troops": initial_troops,
        })
    else:
        await insert_combat_round({
            "history_id": history_id,
            "town_id": town_id,
            "round_num": round_num,
            "state": 1,
            "preload_start_ms": preload_start_ms,
            "preload_end_ms": preload_end_ms,
            "round_start_ms": round_start_ms,
            "round_end_ms": round_end_ms,
            "round_data": round_data,
            "initial_troops": initial_troops,
        })

    if general_kills and history_id:
        kills_list = []
        for (general_id, user_id), data in general_kills.items():
            kills_dict = data.get("kills", {})
            losses_dict = data.get("losses", {})
            elim_set = eliminated_troops.get((general_id, user_id), set())
            kills_list.append({
                "history_id": history_id,
                "round_num": round_num,
                "general_id": general_id,
                "user_id": user_id,
                "kills": [{"兵种名称": name, "数量": count} for name, count in kills_dict.items()],
                "losses": [{"兵种名称": name, "数量": count} for name, count in losses_dict.items()],
                "eliminated_troops": list(elim_set),
            })
        await insert_general_kills(kills_list)

        # 结算本回合武将经验
        gain_exp_map = {}
        death_exp_map = {}
        for item in TROOP_DATA:
            name = item.get("兵种名称")
            exp = item.get("gain_exp", 0)
            death = item.get("death_exp", 0)
            if name:
                if exp:
                    gain_exp_map[name] = exp
                if death:
                    death_exp_map[name] = death
        for item in TROOP_DATA_SPECIAL:
            name = item.get("兵种名称")
            exp = item.get("gain_exp", 0)
            death = item.get("death_exp", 0)
            if name:
                if exp:
                    gain_exp_map[name] = exp
                if death:
                    death_exp_map[name] = death

        for (general_id, user_id), data in general_kills.items():
            total_exp = 0
            for troop_name, count in data.get("kills", {}).items():
                gain_exp_per = gain_exp_map.get(troop_name, 0)
                total_exp += gain_exp_per * count
            for troop_name, count in data.get("losses", {}).items():
                death_exp_per = death_exp_map.get(troop_name, 0)
                total_exp += death_exp_per * count

            if total_exp > 0:
                general = get_general_info(general_id)
                if general:
                    # 武将经验加成（buff）：无加成为0.0不影响原经验值
                    exp_bonus = general.get("exp_bonus", 0.0)
                    if exp_bonus > 0:
                        total_exp = int(total_exp * (1 + exp_bonus))

                    old_level = general.get("level", 0)
                    old_exp = general.get("exp", 0)

                    result = add_exp(general, total_exp)
                    await update_general(general_id, result["updates"])
                    sync_cache_update(general_id, result["updates"])
                else:
                    logger.warning(f"[战斗] 武将 {general_id} (user_id={user_id}) 不在缓存中，无法结算经验")
            else:
                pass

        # 外城战斗回合结束：批量写入武将士气变化（每消灭一支部队+25，上限1000）
        if morale_updates:
            from general.general_db import batch_update_generals
            morale_batch = []
            for general_id, total_morale_gain in morale_updates.items():
                general = get_general_info(general_id)
                if not general:
                    continue
                current_morale = general.get("morale", 100)
                new_morale = min(current_morale + total_morale_gain, 1000)
                if new_morale != current_morale:
                    general["morale"] = new_morale
                    morale_batch.append({
                        "general_id": general_id,
                        "updates": {"morale": new_morale},
                    })
            if morale_batch:
                await batch_update_generals(morale_batch)
                for item in morale_batch:
                    sync_cache_update(item["general_id"], item["updates"])

    await broadcast(make_response("fight_start", "城池战斗回合消息", {
        "type": "town_combat_notify",
        "town_id": town_id,
        "state": "fighting",
        "round_num": round_num,
        "round_start_ms": round_start_ms,
        "round_end_ms": round_end_ms,
    }))

    logger.info(f"城池 {town_id} 第 {round_num} 回合开始，参战部队: {len(troop_order)} 支")


async def _process_round_transition(town_id):
    frv = fight_round_vars.get(town_id)
    if not frv:
        return

    round_num = frv.get("round_num", 0)
    round_start_ms = frv.get("start_time", 0)
    round_end_ms = frv.get("estimated_end_time", 0)

    preload_duration = round_end_ms - round_start_ms
    if preload_duration < PRELOAD_DURATION_MS:
        preload_duration = PRELOAD_DURATION_MS

    preload_start_ms = round_start_ms
    preload_end_ms = round_start_ms + preload_duration

    battle_troops = _get_own_troops_from_grid(town_id)

    newly_arrived = _collect_newly_arrived_troops(
        town_id, preload_start_ms, preload_end_ms
    )
    _assign_gate_positions(newly_arrived, town_id)

    ended, winner, victory_type = check_combat_end(town_id, battle_troops, newly_arrived)

    if ended:
        # 合并所有存活部队到 _battle_troops，统一由 finish_combat 处理
        frv["_battle_troops"] = battle_troops + newly_arrived
        await finish_combat(town_id, winner, victory_type)
        return

    next_round_troops = battle_troops + newly_arrived
    next_round_num = round_num + 1

    fight_round_vars[town_id] = {
        "round_num": next_round_num,
        "is_active": False,
        "start_time": 0,
        "estimated_end_time": 0,
        "preload_start_ms": preload_start_ms,
        "preload_end_ms": preload_end_ms,
        "history_id": frv.get("history_id"),
        "_battle_troops": next_round_troops,
    }

    await _start_round(town_id, next_round_num, next_round_troops)


async def start_first_round(town_id):
    grid_data = fight_round_vars.get(town_id)
    if not grid_data:
        return

    defenders = grid_data.get("_battle_troops", [])
    arriving = _get_and_clear_arriving_troops(town_id)
    _assign_gate_positions(arriving, town_id)

    battle_troops = defenders + arriving
    if not battle_troops:
        return

    for troop in arriving:
        tid = troop["troop_id"]
        if tid in troop_cache:
            troop_cache[tid]["status"] = 3
            troop_cache[tid]["pos"] = town_id
            troop_cache[tid]["dest"] = None
            await update_troop(tid, {"status": 3, "pos": town_id, "dest": None})

    grid_data["_battle_troops"] = battle_troops
    next_round_num = grid_data.get("round_num", 0) + 1

    await _start_round(town_id, next_round_num, battle_troops)


async def _safe_start_first_round(town_id):
    try:
        await start_first_round(town_id)
    except Exception as e:
        logger.error(f"[战斗] 城池 {town_id} 第一回合启动异常: {e}", exc_info=True)


async def _safe_process_round_transition(town_id):
    try:
        await _process_round_transition(town_id)
    except Exception as e:
        logger.error(f"[战斗] 城池 {town_id} 回合转换异常: {e}", exc_info=True)


async def _update_combat_triggers():
    try:
        now_ms = get_uptime_ms()

        for town_id in list(towns_cache.keys()):
            town = towns_cache.get(town_id)
            if not town:
                continue
            status = town.get("status", 0)

            if status == 1:
                frv = fight_round_vars.get(town_id)
                if not frv:
                    continue
                preload_end_ms = frv.get("preload_end_ms", 0)
                if preload_end_ms and now_ms >= preload_end_ms:
                    asyncio.create_task(_safe_start_first_round(town_id))

            elif status == 2:
                frv = fight_round_vars.get(town_id)
                if not frv or not frv.get("calc_completed"):
                    continue

                waiting_until = frv.get("waiting_until")
                if waiting_until and now_ms >= waiting_until:
                    frv["waiting_until"] = None
                    asyncio.create_task(_safe_process_round_transition(town_id))

                elif not waiting_until:
                    estimated_end = frv.get("estimated_end_time", 0)
                    if estimated_end and now_ms >= estimated_end:
                        frv["waiting_until"] = now_ms + 10000
                        logger.info(f"城池 {town_id} 回合 {frv.get('round_num')} 播放完毕，等待10秒")

            elif status == 3:
                frv = fight_round_vars.get(town_id)
                if not frv:
                    towns_cache[town_id]["status"] = 0
                    await update_town_status(town_id, 0)
                    continue
                end_prepare_ms = frv.get("end_prepare_ms", 0)
                if end_prepare_ms and now_ms >= end_prepare_ms:
                    towns_cache[town_id]["status"] = 0
                    await update_town_status(town_id, 0)

                    history_id = frv.get("history_id")
                    if history_id:
                        await update_combat_history(history_id, {"is_finished": 1})

                    winner = frv.get("winner")
                    victory_type = frv.get("victory_type")

                    await broadcast(make_response("fight_end", "城池战斗结束消息", {
                        "type": "town_combat_notify",
                        "town_id": town_id,
                        "state": "normal",
                        "winner": winner,
                        "victory_type": victory_type,
                    }))

                    if town_id in fight_round_vars:
                        del fight_round_vars[town_id]

                    await enter_combat_if_needed(town_id)
                    logger.info(f"城池 {town_id} 战斗结束，恢复正常状态: {victory_type}, 胜利方: {winner}")

    except Exception as e:
        logger.error(f"战斗状态检测异常: {e}")


async def enter_combat_if_needed(town_id):
    town = towns_cache.get(town_id)
    if not town:
        return

    status = town.get("status", 0)
    if status != 0:
        return

    arrived = troops_arrived_at_town.get(town_id, [])
    if not arrived:
        return

    town_owner = town.get("owner")
    has_enemy = False
    for tid in arrived:
        troop = troop_cache.get(tid)
        if not troop:
            continue
        troop_owner = user_nation_cache.get(troop.get("user_id", ""))
        if troop_owner is not None and troop_owner != town_owner:
            has_enemy = True
            break

    if has_enemy:
        await enter_battle_preparation(town_id)