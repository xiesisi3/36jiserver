import copy
import logging
import asyncio

from server_timer.server_timer_core import get_uptime_ms
from data.global_data import (
    towns_cache, troop_cache, fight_round_vars,
)
from towns.towns_outer.town_outer_combat.combat_db import (
    get_unfinished_combat_histories, get_last_combat_round,
    update_combat_history,
)
from towns.towns_outer.town_outer_combat.combat_prepare import (
    check_combat_end, finish_combat, resume_battle_preparation,
)
from towns.towns_outer.town_outer_combat.combat_move import (
    is_troop_alive,
)
from towns.towns_db import update_town_status
from troop.troop_db import update_troop
from core.connection import broadcast
from message.protocol import make_response

logger = logging.getLogger("36ji-server")


def _rebuild_battle_troops_from_round_data(town_id, round_data):
    if not round_data or "troops" not in round_data:
        return []
    troops_data = round_data["troops"]
    battle_troops = []
    for tid_str, rd in troops_data.items():
        tid = int(tid_str)
        troop = troop_cache.get(tid)
        if not troop:
            logger.warning(f"恢复战斗: 部队{tid}不在troop_cache中，跳过")
            continue
        if not is_troop_alive(troop):
            logger.warning(f"恢复战斗: 部队{tid}已死亡，跳过")
            continue
        troop_copy = copy.deepcopy(troop)
        troop_copy["troop_id"] = tid
        troop_copy["grid_pos"] = rd.get("grid_pos")
        troop_copy["team"] = copy.deepcopy(rd.get("team", []))
        troop_copy["food"] = rd.get("food", 0)
        # 恢复时为民兵注入 _nation 字段（义勇军 general_id=-10002，连弩 general_id=-10005，user_id="0"）
        # 民兵在战斗准备阶段生成时已写入 _nation，但服务器重启后从DB恢复时该字段丢失
        # 通过 general_id 识别民兵，补充所属国家信息以正确判断敌我
        if troop_copy.get("general_id") in (-10002, -10005):
            town = towns_cache.get(town_id)
            if town:
                troop_copy["_nation"] = town.get("owner", 0)
        battle_troops.append(troop_copy)
    return battle_troops


async def _fix_troop_pos_dest(town_id, battle_troops):
    for troop in battle_troops:
        tid = troop["troop_id"]
        if tid in troop_cache:
            troop_cache[tid]["pos"] = town_id
            troop_cache[tid]["dest"] = None
            await update_troop(tid, {"pos": town_id, "dest": None})


async def _recover_status_1(town_id, history_id, now_ms):
    defenders = []
    for tid, troop in troop_cache.items():
        if not is_troop_alive(troop):
            continue
        tpos = troop.get("pos")
        tdest = troop.get("dest")
        arrive_time = troop.get("arrive_time", 0) or 0

        if tpos == town_id and troop.get("status") == 3:
            troop_copy = copy.deepcopy(troop)
            troop_copy["troop_id"] = tid
            troop_copy["grid_pos"] = [troop.get("grid_x"), troop.get("grid_y")] if troop.get("grid_x") is not None else None
            # 恢复时为民兵注入 _nation 字段（义勇军 general_id=-10002，连弩 general_id=-10005，user_id="0"）
            if troop_copy.get("general_id") in (-10002, -10005):
                town = towns_cache.get(town_id)
                if town:
                    troop_copy["_nation"] = town.get("owner", 0)
            defenders.append(troop_copy)
        elif tdest == town_id and arrive_time <= now_ms:
            troop_copy = copy.deepcopy(troop)
            troop_copy["troop_id"] = tid
            troop_copy["grid_pos"] = [troop.get("grid_x"), troop.get("grid_y")] if troop.get("grid_x") is not None else None
            # 恢复时为民兵注入 _nation 字段
            if troop_copy.get("general_id") in (-10002, -10005):
                town = towns_cache.get(town_id)
                if town:
                    troop_copy["_nation"] = town.get("owner", 0)
            defenders.append(troop_copy)

    if not defenders:
        logger.warning(f"恢复status=1: 城池{town_id}无部队，标记战斗为已结束")
        await update_combat_history(history_id, {"is_finished": 1})
        towns_cache[town_id]["status"] = 0
        await update_town_status(town_id, 0)
        return

    await _fix_troop_pos_dest(town_id, defenders)

    fight_round_vars[town_id] = {
        "round_num": 0,
        "is_active": False,
        "start_time": 0,
        "estimated_end_time": 0,
        "preload_start_ms": now_ms,
        "preload_end_ms": now_ms,
        "history_id": history_id,
        "_battle_troops": defenders,
        "_defenders": defenders,
        "_arriving": [],
    }

    from towns.towns_outer.town_outer_combat.combat_state import start_first_round
    asyncio.create_task(start_first_round(town_id))

    logger.info(f"城池 {town_id} 战斗准备状态已恢复，部队{len(defenders)}支，立即开始第一回合")


async def _recover_status_2(town_id, history_id, now_ms):
    last_round = await get_last_combat_round(town_id)
    if not last_round:
        logger.warning(f"恢复status=2: 城池{town_id}无回合数据，标记战斗为已结束")
        await update_combat_history(history_id, {"is_finished": 1})
        towns_cache[town_id]["status"] = 0
        await update_town_status(town_id, 0)
        return

    round_data = last_round.get("round_data", {})
    if isinstance(round_data, str):
        import json
        round_data = json.loads(round_data)

    battle_troops = _rebuild_battle_troops_from_round_data(town_id, round_data)
    await _fix_troop_pos_dest(town_id, battle_troops)

    ended, winner, victory_type = check_combat_end(town_id, battle_troops, [])
    if ended:
        fight_round_vars[town_id] = {
            "round_num": last_round.get("round_num", 0),
            "is_active": False,
            "history_id": history_id,
            "_battle_troops": battle_troops,
        }
        await finish_combat(town_id, winner, victory_type)
        logger.info(f"城池 {town_id} 恢复后直接结束: {victory_type}, 胜利方={winner}")
    else:
        await resume_battle_preparation(town_id, history_id, battle_troops, last_round.get("round_num", 0))
        logger.info(f"城池 {town_id} 战斗中状态已恢复为预加载，history_id={history_id}")


async def _recover_status_3(town_id, history_id, now_ms):
    last_round = await get_last_combat_round(town_id)
    if not last_round:
        logger.warning(f"恢复status=3: 城池{town_id}无回合数据，标记战斗为已结束")
        await update_combat_history(history_id, {"is_finished": 1})
        towns_cache[town_id]["status"] = 0
        await update_town_status(town_id, 0)
        return

    round_num = last_round.get("round_num", 0)
    end_prepare_ms = last_round.get("round_end_ms", 0) + 30000

    fight_round_vars[town_id] = {
        "round_num": round_num,
        "is_active": False,
        "end_prepare_ms": end_prepare_ms,
        "history_id": history_id,
    }

    if end_prepare_ms and now_ms >= end_prepare_ms:
        await update_combat_history(history_id, {"is_finished": 1})
        towns_cache[town_id]["status"] = 0
        await update_town_status(town_id, 0)

        await broadcast(make_response("fight_end", "城池战斗结束消息", {
            "type": "town_combat_notify",
            "town_id": town_id,
            "state": "normal",
        }))

        if town_id in fight_round_vars:
            del fight_round_vars[town_id]

        from towns.towns_outer.town_outer_combat.combat_state import enter_combat_if_needed
        await enter_combat_if_needed(town_id)

    logger.info(f"城池 {town_id} 结束准备状态已恢复，end_prepare_ms={end_prepare_ms}")


async def recover_combat_state():
    now_ms = get_uptime_ms()

    unfinished = await get_unfinished_combat_histories()
    if not unfinished:
        logger.info("战斗状态恢复: 没有未结束的战斗记录")
        return

    for history in unfinished:
        history_id = history["id"]
        town_id = history["town_id"]
        town = towns_cache.get(town_id)
        if not town:
            logger.warning(f"恢复战斗 history_id={history_id}: 城池{town_id}不存在，标记战斗为已结束")
            await update_combat_history(history_id, {"is_finished": 1})
            continue

        status = town.get("status", 0)
        logger.info(f"恢复战斗 history_id={history_id}, 城池{town_id}, status={status}")

        if status == 1:
            await _recover_status_1(town_id, history_id, now_ms)
        elif status == 2:
            await _recover_status_2(town_id, history_id, now_ms)
        elif status == 3:
            await _recover_status_3(town_id, history_id, now_ms)
        else:
            logger.warning(f"恢复战斗 history_id={history_id}: 城池{town_id} status={status} 异常，标记战斗为已结束")
            await update_combat_history(history_id, {"is_finished": 1})

    logger.info("战斗状态恢复完成")