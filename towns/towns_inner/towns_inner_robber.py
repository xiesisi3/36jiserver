# 内城剿匪功能
# 参考 towns_inner_recruit.py 的接口规范

import copy
import json
import logging
from datetime import datetime

from core.connection import send_message
from message.protocol import make_response
from message.combat_guard import require_town_peace
from data.global_data import (
    troop_cache, generals_cache, user_resource_cache, clients,
    robber_daily, towns_cache,
)
from combat.combat_constants import (
    ROBBER_DIFFICULTY_CONFIG, ROBBER_DAILY_LIMIT,
    ROBBER_GOLD_COST, ROBBER_GOLD_EXP_BONUS,
)
from combat.combat_utils import (
    generate_enemy_troop, build_combat_troop, calc_round_food_cost,
    recalc_troop_food,
)
from combat.combat_core import run_robber_battle
from troop.troop_db import update_troop as update_troop_db
from troop.troop_utils import calculate_total_troops
from general.general_db import update_general
from general.general_core import add_exp, sync_cache_update
from user_resource.user_resource_db import update_user_resource_field
from towns.towns_db import update_town_attrs

logger = logging.getLogger('36ji-server')

VALID_DIFFICULTIES = list(ROBBER_DIFFICULTY_CONFIG.keys())


async def handle_robber_quota(websocket, client_id, msg):
    """查询剿匪剩余次数（跨天自动重置）
    返回: {remaining: int, daily_limit: int}
    """
    user_id = clients.get(client_id, {}).get("user_id")

    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    remaining = _get_or_refresh_robber_daily(user_id)
    await send_message(websocket, make_response("success", "剿匪剩余次数", {
        "remaining": remaining,
        "daily_limit": ROBBER_DAILY_LIMIT,
    }))


@require_town_peace
async def handle_robber_fight(websocket, client_id, msg):
    """剿匪战斗
    入参: data.troop_id - 部队ID, data.difficulty - 难度(极易/简单/普通/困难/极难),
          data.use_gold - 是否使用黄金剿匪(bool)
    返回: 战斗快照 + 经验信息 + 部队状态 + 剩余次数
    """
    data = msg.get("data", {})
    user_id = clients.get(client_id, {}).get("user_id")
    troop_id = data.get("troop_id")
    difficulty = (data.get("difficulty") or "").strip()
    use_gold = data.get("use_gold", False)

    logger.info(f"[剿匪] 收到请求 user_id={user_id} troop_id={troop_id} difficulty={difficulty} use_gold={use_gold}")
    logger.info(f"[剿匪] 完整请求JSON: {json.dumps(msg, ensure_ascii=False)}")

    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    if not troop_id:
        await send_message(websocket, make_response("error", "缺少部队ID", ""))
        return

    if difficulty not in VALID_DIFFICULTIES:
        await send_message(websocket, make_response("error",
            f"无效的难度，请选择: {', '.join(VALID_DIFFICULTIES)}", ""))
        return

    troop = troop_cache.get(troop_id)
    if troop is None:
        await send_message(websocket, make_response("error", "部队不存在", ""))
        return

    if troop.get("user_id") != user_id:
        await send_message(websocket, make_response("error", "部队不属于该用户", ""))
        return

    if troop.get("status") != 1:
        await send_message(websocket, make_response("error", "部队当前状态无法剿匪，需为驻守状态", ""))
        return

    town_id = troop.get("pos")
    if town_id is None or town_id <= 0:
        await send_message(websocket, make_response("error", "部队未驻守城池，无法剿匪", ""))
        return

    total_troops = calculate_total_troops(troop.get("team", []))
    if total_troops <= 0:
        await send_message(websocket, make_response("error", "部队没有兵力，无法剿匪", ""))
        return

    round_food = calc_round_food_cost(troop)
    if troop.get("food", 0) < round_food:
        await send_message(websocket, make_response("error",
            f"粮食不足，一回合需要{round_food}，当前{troop.get('food', 0)}", ""))
        return

    if use_gold:
        resource = user_resource_cache.get(user_id)
        if resource is None:
            await send_message(websocket, make_response("error", "用户资源不存在", ""))
            return
        gold = resource.get("gold", 0)
        if gold < ROBBER_GOLD_COST:
            await send_message(websocket, make_response("error",
                f"黄金不足，需要{ROBBER_GOLD_COST}，当前{gold}", ""))
            return
        await update_user_resource_field(user_id, "gold", gold - ROBBER_GOLD_COST)
        user_resource_cache[user_id]["gold"] = gold - ROBBER_GOLD_COST
    else:
        remaining = _get_or_refresh_robber_daily(user_id)
        if remaining <= 0:
            await send_message(websocket, make_response("error", "今日剿匪次数已用完", ""))
            return
        robber_daily[user_id]["count"] -= 1

    general_id = troop["general_id"]
    general = None
    for g in generals_cache.get(user_id, []):
        if g["id"] == general_id:
            general = g
            break

    if general is None:
        await send_message(websocket, make_response("error", "武将不存在", ""))
        return

    if general.get("status") != 1:
        await send_message(websocket, make_response("error", "武将当前状态异常，无法剿匪", ""))
        return

    player_troop = build_combat_troop(troop_id, troop, general, user_id)
    enemy_troop = generate_enemy_troop(difficulty)

    battle_result = run_robber_battle(player_troop, enemy_troop)

    total_exp = battle_result["total_exp"]
    result = battle_result["result"]
    logger.info(f"[剿匪] 战斗完成 user_id={user_id} troop_id={troop_id} "
                f"基础经验={total_exp} 胜负={result['w']} "
                f"玩家兵力={result['tc']} 敌方兵力={result['ec']}")

    if use_gold:
        total_exp = int(total_exp * ROBBER_GOLD_EXP_BONUS)

    exp_result = add_exp(general, total_exp)

    await update_general(general_id, exp_result["updates"])
    sync_cache_update(general_id, exp_result["updates"])

    updated_player = battle_result["player_troop"]
    recalc_troop_food(updated_player)
    troop_updates = {
        "team": updated_player["team"],
        "food": updated_player["food"],
    }
    await update_troop_db(troop_id, troop_updates)
    troop["team"] = updated_player["team"]
    troop["food"] = updated_player["food"]

    town = towns_cache.get(town_id)
    town_stability_old = town.get("stability", 0) if town else 0
    town_popular_old = town.get("popular_support", 0) if town else 0
    town_stability_new = town_stability_old
    town_popular_new = town_popular_old
    stability_gain = 0

    if town and battle_result["result"].get("w") == 1:
        enemy_initial = battle_result["init"]["R"][0]["c"]
        enemy_final = battle_result["result"]["ec"]
        enemy_killed = enemy_initial - enemy_final

        cfg = ROBBER_DIFFICULTY_CONFIG.get(difficulty, {})
        stability_factor = cfg.get("stability_factor", 1.0)

        stability_gain = int(stability_factor * enemy_killed)
        if stability_gain > 0:
            town_stability_new = min(town_stability_old + stability_gain, 100000)
            town["stability"] = town_stability_new

        if town_popular_old < 10000:
            popular_gain = stability_gain // 10
            if popular_gain > 0:
                town_popular_new = min(town_popular_old + popular_gain, 10000)
                town["popular_support"] = town_popular_new

        if stability_gain > 0:
            await update_town_attrs(town_id, {
                "stability": town_stability_new,
                "popular_support": town_popular_new,
            })

    resource = user_resource_cache.get(user_id)
    robber_score_old = resource.get("robber_score", 0) if resource else 0
    robber_score_new = robber_score_old + stability_gain
    if resource and stability_gain > 0:
        await update_user_resource_field(user_id, "robber_score", robber_score_new)
        user_resource_cache[user_id]["robber_score"] = robber_score_new
    else:
        robber_score_new = robber_score_old

    result_data = copy.deepcopy(battle_result["result"])
    result_data["e"] = total_exp

    response = {
        "init": battle_result["init"],
        "rounds": battle_result["rounds"],
        "result": result_data,
        "exp": {
            "leveled_up": exp_result["leveled_up"],
            "new_level": exp_result["new_level"],
            "new_exp": exp_result["new_exp"],
            "levels_gained": exp_result["levels_gained"],
            "skill_points": general["skill_points"],
        },
        "troop": {
            "food": updated_player["food"],
            "team": [s.get("数量", 0) if s else 0 for s in updated_player["team"]],
        },
        "town_attrs": {
            "stability": town_stability_new,
            "popular_support": town_popular_new,
        },
        "robber_score": {
            "old": robber_score_old,
            "new": robber_score_new,
        },
    }

    if not use_gold:
        response["daily_remaining"] = robber_daily[user_id]["count"]

    logger.info(f"[剿匪] 返回响应 summary user_id={user_id} troop_id={troop_id} "
                f"总经验={total_exp} 升级={exp_result['leveled_up']} 新等级={exp_result['new_level']} "
                f"部队粮食={updated_player['food']} 部队兵力={[s.get('数量',0) if s else 0 for s in updated_player['team']]}")

    full_response = make_response("success", "剿匪战斗完成", response)
    logger.info(f"[剿匪] 完整响应JSON: {json.dumps(full_response, ensure_ascii=False)}")
    await send_message(websocket, full_response)


def _get_or_refresh_robber_daily(user_id):
    """获取或刷新剿匪每日次数（跨自然天自动重置为100）
    返回: 剩余次数 (int)
    """
    today = datetime.now().strftime("%Y-%m-%d")
    daily = robber_daily.get(user_id)

    if daily is None or daily.get("date") != today:
        robber_daily[user_id] = {"count": ROBBER_DAILY_LIMIT, "date": today}
        return ROBBER_DAILY_LIMIT

    return max(daily["count"], 0)