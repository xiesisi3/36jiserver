import json
import logging

from core.connection import send_message
from message.protocol import make_response
from message.combat_guard import require_town_peace
from data.global_data import (
    troop_cache, towns_cache, generals_cache, user_resource_cache, clients,
    user_nation_cache,
)
from troop.troop_utils import calculate_total_troops
from towns.towns_db import update_town_attrs
from general.general_db import update_general
from general.general_core import add_exp, sync_cache_update
from user_resource.user_resource_db import update_user_resource_field

logger = logging.getLogger('36ji-server')

REPAIR_COPPER_PER_SOLDIER = 5


@require_town_peace
async def handle_town_repair(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = clients.get(client_id, {}).get("user_id")
    troop_id = data.get("troop_id")
    repair_type = (data.get("repair_type") or "").strip()

    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    if not troop_id:
        await send_message(websocket, make_response("error", "缺少部队ID", ""))
        return

    if repair_type not in ("road", "wall"):
        await send_message(websocket, make_response("error", "无效的修缮类型，请选择 road 或 wall", ""))
        return

    troop = troop_cache.get(troop_id)
    if troop is None:
        await send_message(websocket, make_response("error", "部队不存在", ""))
        return

    if troop.get("user_id") != user_id:
        await send_message(websocket, make_response("error", "部队不属于该用户", ""))
        return

    if troop.get("status") != 1:
        await send_message(websocket, make_response("error", "部队当前状态无法修缮，需为驻守状态", ""))
        return

    town_id = troop.get("pos")
    if town_id is None or town_id <= 0:
        await send_message(websocket, make_response("error", "部队未驻守城池，无法修缮", ""))
        return

    town = towns_cache.get(town_id)
    if town is None:
        await send_message(websocket, make_response("error", "城池不存在", ""))
        return

    user_nation = user_nation_cache.get(user_id)
    town_owner = town.get("owner")
    if user_nation is None:
        await send_message(websocket, make_response("error", "用户未选择国家", ""))
        return
    if user_nation != town_owner:
        await send_message(websocket, make_response("error", "只能修缮本国的城池", ""))
        return

    total_soldiers = calculate_total_troops(troop.get("team", []))
    if total_soldiers <= 0:
        await send_message(websocket, make_response("error", "部队没有兵力，无法修缮", ""))
        return

    copper_cost = total_soldiers * REPAIR_COPPER_PER_SOLDIER

    resource = user_resource_cache.get(user_id)
    if resource is None:
        await send_message(websocket, make_response("error", "用户资源不存在", ""))
        return
    if resource.get("copper", 0) < copper_cost:
        await send_message(websocket, make_response("error",
            f"铜币不足，需要{copper_cost}，当前{resource.get('copper', 0)}", ""))
        return

    general_id = troop.get("general_id")
    general = None
    for g in generals_cache.get(user_id, []):
        if g["id"] == general_id:
            general = g
            break

    if general is None:
        await send_message(websocket, make_response("error", "武将不存在", ""))
        return

    if general.get("status") != 1:
        await send_message(websocket, make_response("error", "武将当前状态异常，无法修缮", ""))
        return

    governance_phase = general.get("governance_phase", 0)
    intelligence = general.get("intelligence", 0)

    increase = copper_cost * (1 + governance_phase * 0.20) * (1 + intelligence / 100)
    increase = int(increase)

    attr_key = "traffic" if repair_type == "road" else "defense"
    attr_name = "交通" if repair_type == "road" else "防御"

    old_value = town.get(attr_key, 0)
    new_value = min(old_value + increase, 100000)
    actual_increase = new_value - old_value
    town[attr_key] = new_value

    popular_support = town.get("popular_support", 0)
    popular_support_old = popular_support
    if popular_support < 10000:
        popular_gain = increase // 10
        if popular_gain > 0:
            popular_support = min(popular_support + popular_gain, 10000)
            town["popular_support"] = popular_support

    await update_user_resource_field(user_id, "copper", resource["copper"] - copper_cost)
    user_resource_cache[user_id]["copper"] = resource["copper"] - copper_cost

    score_key = "road_repair_score" if repair_type == "road" else "wall_repair_score"
    old_score = resource.get(score_key, 0)
    new_score = old_score + increase
    await update_user_resource_field(user_id, score_key, new_score)
    user_resource_cache[user_id][score_key] = new_score

    await update_town_attrs(town_id, {
        attr_key: new_value,
        "popular_support": popular_support,
    })

    exp_result = add_exp(general, increase, use_wisdom=False)

    await update_general(general_id, exp_result["updates"])
    sync_cache_update(general_id, exp_result["updates"])

    logger.info(f"[修缮] user_id={user_id} troop_id={troop_id} town_id={town_id} "
                f"type={repair_type} 总兵力={total_soldiers} 铜币消耗={copper_cost} "
                f"提升值={increase} 实际={actual_increase} "
                f"旧值={old_value} 新值={new_value} "
                f"民心={popular_support_old}→{popular_support} "
                f"武将经验={increase} 升级={exp_result['leveled_up']}")

    response = {
        "repair_type": repair_type,
        "copper_cost": copper_cost,
        "increase": increase,
        "actual_increase": actual_increase,
        "old_value": old_value,
        "new_value": new_value,
        "popular_support": popular_support,
        "exp": {
            "leveled_up": exp_result["leveled_up"],
            "new_level": exp_result["new_level"],
            "new_exp": exp_result["new_exp"],
            "levels_gained": exp_result["levels_gained"],
            "skill_points": general["skill_points"],
        },
        "score": {
            "key": score_key,
            "old": old_score,
            "new": new_score,
        },
    }

    full_response = make_response("success", f"修缮{attr_name}完成", response)
    await send_message(websocket, full_response)