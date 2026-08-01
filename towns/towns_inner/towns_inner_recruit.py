import random
import time
import uuid
import logging
from datetime import datetime

from core.connection import send_message
from message.protocol import make_response
from general.general_db import (
    insert_general,
    get_general_by_id,
)
from general.general_core import (
    draw_fixed_hero,
    generate_random_general,
    hero_panel_to_db_format,
    sync_cache_insert,
)
from user_resource.user_resource_db import update_user_resource_field
from data.global_data import user_resource_cache, recruit_cache, recruit_copper_daily, recruit_pity_counter, generals_cache
from tech.tech_core import get_general_limit, ensure_tech

logger = logging.getLogger('36ji-server')

RECRUIT_EXPIRE_SECONDS = 60
COPPER_COST = 100
GOLD_COST = 100
COPPER_DAILY_LIMIT = 20


async def handle_recruit_copper_quota(websocket, client_id, msg):
    """查询铜钱招募剩余次数（跨天自动重置）
    入参: data.user_id - 用户ID
    返回: {remaining: int, daily_limit: int}
    """
    data = msg.get("data", {})
    user_id = (data.get("user_id") or "").strip()

    if not user_id:
        await send_message(websocket, make_response("error", "缺少用户ID", ""))
        return

    remaining = _get_or_refresh_copper_daily(user_id)
    await send_message(websocket, make_response("success", "铜钱招募剩余次数", {
        "remaining": remaining,
        "daily_limit": COPPER_DAILY_LIMIT,
    }))


async def handle_recruit_pre(websocket, client_id, msg):
    """第一步：预招募，校验资源并扣减，抽取武将并返回面板数据 + 令牌，缓存60秒
    入参: data.user_id - 用户ID, data.payment_type - "copper" / "gold"
    返回: {recruit_id, recruit_type, panel, expire_seconds}
    """
    data = msg.get("data", {})
    user_id = (data.get("user_id") or "").strip()
    payment_type = (data.get("payment_type") or "").strip()

    if not user_id:
        await send_message(websocket, make_response("error", "缺少用户ID", ""))
        return

    if payment_type not in ("copper", "gold"):
        await send_message(websocket, make_response("error", "无效的招募方式，请选择 copper 或 gold", ""))
        return

    if payment_type == "copper":
        remaining = _get_or_refresh_copper_daily(user_id)
        if remaining <= 0:
            await send_message(websocket, make_response("error", "今日铜钱招募次数已用完", ""))
            return

        resource = user_resource_cache.get(user_id)
        if resource is None:
            await send_message(websocket, make_response("error", "用户资源不存在", ""))
            return

        copper = resource.get("copper", 0)
        if copper < COPPER_COST:
            await send_message(websocket, make_response("error", f"铜钱不足，需要{COPPER_COST}铜钱，当前仅有{copper}", ""))
            return

        await update_user_resource_field(user_id, "copper", copper - COPPER_COST)
        user_resource_cache[user_id]["copper"] = copper - COPPER_COST
        recruit_copper_daily[user_id]["count"] -= 1

    else:
        resource = user_resource_cache.get(user_id)
        if resource is None:
            await send_message(websocket, make_response("error", "用户资源不存在", ""))
            return

        gold = resource.get("gold", 0)
        if gold < GOLD_COST:
            await send_message(websocket, make_response("error", f"黄金不足，需要{GOLD_COST}黄金，当前仅有{gold}", ""))
            return

        await update_user_resource_field(user_id, "gold", gold - GOLD_COST)
        user_resource_cache[user_id]["gold"] = gold - GOLD_COST

    pity = recruit_pity_counter.get(user_id, 0)
    if pity >= 9:
        panel = draw_fixed_hero(user_id)
        if panel is None:
            panel = generate_random_general(user_id)
            recruit_type = "random"
        else:
            recruit_type = "fixed"
    elif random.random() < 0.2:
        panel = draw_fixed_hero(user_id)
        if panel is None:
            panel = generate_random_general(user_id)
            recruit_type = "random"
        else:
            recruit_type = "fixed"
    else:
        panel = generate_random_general(user_id)
        recruit_type = "random"

    if recruit_type == "fixed":
        recruit_pity_counter[user_id] = 0
    else:
        recruit_pity_counter[user_id] = pity + 1

    if panel is None:
        remaining = _get_or_refresh_copper_daily(user_id)
        await send_message(websocket, make_response("error", "招募失败，英雄池为空", ""))
        return

    recruit_id = uuid.uuid4().hex[:8]
    recruit_cache[user_id] = {
        "recruit_id": recruit_id,
        "panel": panel,
        "expire_at": time.monotonic() + RECRUIT_EXPIRE_SECONDS,
    }

    await send_message(websocket, make_response("success", "预招募成功", {
        "recruit_id": recruit_id,
        "recruit_type": recruit_type,
        "panel": panel,
        "expire_seconds": RECRUIT_EXPIRE_SECONDS,
    }))


async def handle_recruit_confirm(websocket, client_id, msg):
    """第二步：确认招募，校验令牌，通过后入库并加入全局武将缓存
    入参: data.user_id - 用户ID, data.recruit_id - 预招募令牌
    返回: {recruit_type, general: {...}}
    """
    data = msg.get("data", {})
    user_id = (data.get("user_id") or "").strip()
    recruit_id = data.get("recruit_id")

    if not user_id:
        await send_message(websocket, make_response("error", "缺少用户ID", ""))
        return

    if not recruit_id:
        await send_message(websocket, make_response("error", "缺少招募令牌", ""))
        return

    cached = recruit_cache.get(user_id)
    if cached is None:
        await send_message(websocket, make_response("error", "请先进行预招募", ""))
        return

    if cached["recruit_id"] != recruit_id:
        await send_message(websocket, make_response("error", "招募令牌无效", ""))
        return

    if time.monotonic() > cached["expire_at"]:
        del recruit_cache[user_id]
        await send_message(websocket, make_response("error", "招募已过期，请重新预招募", ""))
        return

    panel = cached["panel"]
    del recruit_cache[user_id]

    recruit_type = "fixed" if "skill_name" in panel and panel.get("skill_name") != "无" else "random"

    await ensure_tech(user_id)
    current_count = len([g for g in generals_cache.get(user_id, []) if g.get("id", 0) > 0])
    limit = get_general_limit(user_id)
    if current_count >= limit:
        await send_message(websocket, make_response("error", f"武将数量已达上限({limit}个)，请升级世卿世禄科技", ""))
        return

    db_data = hero_panel_to_db_format(panel, user_id)
    general_id = await insert_general(db_data)

    general = await get_general_by_id(general_id)
    if general is None:
        await send_message(websocket, make_response("error", "招募后查询失败", ""))
        return

    await send_message(websocket, make_response("success", "招募成功", {
        "recruit_type": recruit_type,
        "general": general,
    }))
    sync_cache_insert(general)


def _get_or_refresh_copper_daily(user_id):
    """获取或刷新铜钱招募每日次数（跨自然天自动重置为20）
    返回: 剩余次数 (int)
    """
    today = datetime.now().strftime("%Y-%m-%d")
    daily = recruit_copper_daily.get(user_id)

    if daily is None or daily.get("date") != today:
        recruit_copper_daily[user_id] = {"count": COPPER_DAILY_LIMIT, "date": today}
        return COPPER_DAILY_LIMIT

    return max(daily["count"], 0)