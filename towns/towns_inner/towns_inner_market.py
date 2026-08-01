# 内城市集功能：资源互换

import logging
from core.connection import send_message
from message.protocol import make_response
from data.global_data import user_resource_cache, clients
from user_resource.user_resource_db import update_user_resource_field

logger = logging.getLogger('36ji-server')

EXCHANGE_GOLD_COST = 20

RATE = {
    "wood": 1.0,
    "grain": 1.5,
    "iron": 3.0,
}

RESOURCE_FIELDS = ["wood", "grain", "iron"]


def _calc_value(resources):
    """计算资源总价值（木材等价值）"""
    return sum(resources.get(f, 0) * RATE[f] for f in RESOURCE_FIELDS)


def _validate_amounts(resources):
    """校验资源数量：均为非负整数，至少一项 > 0"""
    for f in RESOURCE_FIELDS:
        v = resources.get(f, 0)
        if not isinstance(v, int) or v < 0:
            return False, f"{f} 必须为非负整数"
    if sum(resources.get(f, 0) for f in RESOURCE_FIELDS) < 1:
        return False, "至少需要提供/需求一种资源"
    return True, None


def _check_value_match(provide, request):
    """检查前后总价值是否精确相等"""
    provide_value = _calc_value(provide)
    request_value = _calc_value(request)
    if abs(provide_value - request_value) < 0.001:
        return True, None
    return False, f"资源价值不匹配，提供={provide_value}，需求={request_value}"


async def handle_market_exchange(websocket, client_id, msg):
    """市集资源互换"""
    user_id = clients.get(client_id, {}).get("user_id")
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    data = msg.get("data", {})
    provide = data.get("provide", {})
    request = data.get("request", {})

    if not isinstance(provide, dict) or not isinstance(request, dict):
        await send_message(websocket, make_response("error", "资源格式错误", ""))
        return

    valid, err = _validate_amounts(provide)
    if not valid:
        await send_message(websocket, make_response("error", f"提供资源: {err}", ""))
        return

    valid, err = _validate_amounts(request)
    if not valid:
        await send_message(websocket, make_response("error", f"需求资源: {err}", ""))
        return

    match, err = _check_value_match(provide, request)
    if not match:
        await send_message(websocket, make_response("error", err, ""))
        return

    resource = user_resource_cache.get(user_id)
    if not resource:
        await send_message(websocket, make_response("error", "用户资源不存在", ""))
        return

    for f in RESOURCE_FIELDS:
        need = provide.get(f, 0)
        if need > resource.get(f, 0):
            await send_message(websocket, make_response("error", f"{f} 不足，需要{need}，当前{resource.get(f, 0)}", ""))
            return

    gold = resource.get("gold", 0)
    if gold < EXCHANGE_GOLD_COST:
        await send_message(websocket, make_response("error", f"黄金不足，需要{EXCHANGE_GOLD_COST}，当前{gold}", ""))
        return

    for f in RESOURCE_FIELDS:
        resource[f] = resource.get(f, 0) - provide.get(f, 0) + request.get(f, 0)
    resource["gold"] = gold - EXCHANGE_GOLD_COST

    await update_user_resource_field(user_id, "gold", resource["gold"])
    for f in RESOURCE_FIELDS:
        await update_user_resource_field(user_id, f, resource[f])

    logger.info(f"用户 {user_id} 市集兑换: 提供 {provide} 需求 {request} 消耗黄金 {EXCHANGE_GOLD_COST}")

    await send_message(websocket, make_response("success", "兑换成功", {
        "provide": {f: provide.get(f, 0) for f in RESOURCE_FIELDS},
        "request": {f: request.get(f, 0) for f in RESOURCE_FIELDS},
        "gold_cost": EXCHANGE_GOLD_COST,
        "gold_remaining": resource["gold"],
    }))