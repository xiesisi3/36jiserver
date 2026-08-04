import logging

from core.connection import send_message
from message.protocol import make_response
from data.global_data import troop_cache, user_resource_cache
from general.general_db import (
    get_general_by_id,
    get_generals_by_user,
    update_general,
    delete_general,
)
from general.general_core import (
    add_exp,
    add_attribute_point,
    upgrade_talent,
    STATUS_MAP,
    sync_cache_update,
    sync_cache_delete,
)

logger = logging.getLogger('36ji-server')


async def handle_general_list(websocket, client_id, msg):
    """查询用户的所有武将列表
    入参: data.user_id - 用户ID
    返回: {generals: [...], count: int}
    """
    data = msg.get("data", {})
    user_id = (data.get("user_id") or "").strip()

    if not user_id:
        await send_message(websocket, make_response("error", "缺少用户ID", ""))
        return

    generals = await get_generals_by_user(user_id)

    general_troop_map = {}
    for tid, t in troop_cache.items():
        gid = t.get("general_id")
        if gid and gid > 0:
            general_troop_map[gid] = t

    for g in generals:
        if g.get("status") == 2:
            troop = general_troop_map.get(g["id"])
            g["estimated_arrival_time"] = troop["arrive_time"] if troop else None
        else:
            g["estimated_arrival_time"] = None

    await send_message(websocket, make_response("success", "武将列表", {
        "generals": generals,
        "count": len(generals),
    }))


async def handle_general_detail(websocket, client_id, msg):
    """通过武将ID查询单个武将详细信息
    入参: data.general_id - 武将ID
    返回: 武将完整字段字典，附加 status_text 中文状态描述
    """
    data = msg.get("data", {})
    general_id = data.get("general_id")

    if not general_id:
        await send_message(websocket, make_response("error", "缺少武将ID", ""))
        return

    general = await get_general_by_id(general_id)
    if general is None:
        await send_message(websocket, make_response("error", "武将不存在", ""))
        return

    general["status_text"] = STATUS_MAP.get(general.get("status"), "未知")
    await send_message(websocket, make_response("success", "武将详情", general))


async def handle_general_add_exp(websocket, client_id, msg):
    """给武将增加经验值，自动触发升级和技能点发放，升级时按性格增加初始属性
    入参: data.general_id - 武将ID, data.exp - 获得的经验值(int)
    返回: {general_id, gained_exp, leveled_up, new_level, new_exp, levels_gained, skill_points}
    """
    data = msg.get("data", {})
    general_id = data.get("general_id")
    gained_exp = data.get("exp", 0)

    if not general_id:
        await send_message(websocket, make_response("error", "缺少武将ID", ""))
        return

    if not isinstance(gained_exp, int) or gained_exp <= 0:
        await send_message(websocket, make_response("error", "经验值无效", ""))
        return

    general = await get_general_by_id(general_id)
    if general is None:
        await send_message(websocket, make_response("error", "武将不存在", ""))
        return

    if general.get("status") == 4:
        await send_message(websocket, make_response("error", "武将已阵亡，无法操作", ""))
        return

    result = add_exp(general, gained_exp)

    await update_general(general_id, result["updates"])

    await send_message(websocket, make_response("success", "经验增加成功", {
        "general_id": general_id,
        "gained_exp": gained_exp,
        "leveled_up": result["leveled_up"],
        "new_level": result["new_level"],
        "new_exp": result["new_exp"],
        "levels_gained": result["levels_gained"],
        "skill_points": general["skill_points"],
    }))
    sync_cache_update(general_id, result["updates"])


async def handle_general_add_attr(websocket, client_id, msg):
    """消耗技能点为武将提升属性，可同时增加多个属性
    入参: data.general_id - 武将ID, data.attrs - 属性分配 {"force": 2, "intelligence": 1}
    返回: {general_id, attrs, skill_points}
    """
    data = msg.get("data", {})
    general_id = data.get("general_id")
    attrs = data.get("attrs")

    if not general_id:
        await send_message(websocket, make_response("error", "缺少武将ID", ""))
        return

    if not isinstance(attrs, dict) or not attrs:
        await send_message(websocket, make_response("error", "请指定属性分配(attrs: {force/intelligence/charisma: 点数})", ""))
        return

    general = await get_general_by_id(general_id)
    if general is None:
        await send_message(websocket, make_response("error", "武将不存在", ""))
        return

    if general.get("status") == 4:
        await send_message(websocket, make_response("error", "武将已阵亡，无法操作", ""))
        return

    success, message = add_attribute_point(general, attrs)
    if not success:
        await send_message(websocket, make_response("error", message, ""))
        return

    updates = {
        "force": general["force"],
        "intelligence": general["intelligence"],
        "charisma": general["charisma"],
        "skill_points": general["skill_points"],
    }
    await update_general(general_id, updates)

    await send_message(websocket, make_response("success", message, {
        "general_id": general_id,
        "attrs": attrs,
        "skill_points": general["skill_points"],
    }))
    sync_cache_update(general_id, updates)


async def handle_general_update_status(websocket, client_id, msg):
    """更新武将状态（编组/行军/战斗/死亡等）
    入参: data.general_id - 武将ID, data.status - 状态码(0-4),
          data.pos(可选) - 所处位置, data.dest(可选) - 目的地,
          data.death_time(可选) - 阵亡时间(毫秒时间戳)
    返回: {general_id, status, status_text}
    """
    data = msg.get("data", {})
    general_id = data.get("general_id")
    status = data.get("status")
    pos = data.get("pos")
    dest = data.get("dest")
    death_time = data.get("death_time")

    if not general_id:
        await send_message(websocket, make_response("error", "缺少武将ID", ""))
        return

    if status is None:
        await send_message(websocket, make_response("error", "缺少状态值", ""))
        return

    general = await get_general_by_id(general_id)
    if general is None:
        await send_message(websocket, make_response("error", "武将不存在", ""))
        return

    updates = {"status": status}
    if pos is not None:
        updates["pos"] = pos
    if dest is not None:
        updates["dest"] = dest
    if death_time is not None:
        updates["death_time"] = death_time

    if status == 4:
        updates.update({
            "morale": 100,
            "attack_bonus": 0.0,
            "defense_bonus": 0.0,
            "hp_bonus": 0.0,
            "exp_bonus": 0.0,
            "morale_bonus": 0.0,
            "attack_bonus_expire": None,
            "defense_bonus_expire": None,
            "hp_bonus_expire": None,
            "exp_bonus_expire": None,
            "morale_bonus_expire": None,
        })

    await update_general(general_id, updates)

    await send_message(websocket, make_response("success", "状态更新成功", {
        "general_id": general_id,
        "status": status,
        "status_text": STATUS_MAP.get(status, "未知"),
    }))
    sync_cache_update(general_id, updates)


async def handle_general_talent_upgrade(websocket, client_id, msg):
    """武将天赋升级
    入参: data.general_id - 武将ID, data.talent_name - 天赋名(一鼓作气/勇冠三军/大将之材/铜墙铁壁)
    返回: {general_id, talent_name, new_level, talent_skill}
    """
    data = msg.get("data", {})
    general_id = data.get("general_id")
    talent_name = (data.get("talent_name") or "").strip()

    if not general_id:
        await send_message(websocket, make_response("error", "缺少武将ID", ""))
        return

    if not talent_name:
        await send_message(websocket, make_response("error", "缺少天赋名", ""))
        return

    general = await get_general_by_id(general_id)
    if general is None:
        await send_message(websocket, make_response("error", "武将不存在", ""))
        return

    if general.get("status") == 4:
        await send_message(websocket, make_response("error", "武将已阵亡，无法操作", ""))
        return

    success, message, updates = upgrade_talent(general, talent_name)
    if not success:
        await send_message(websocket, make_response("error", message, ""))
        return

    await update_general(general_id, updates)

    await send_message(websocket, make_response("success", message, {
        "general_id": general_id,
        "talent_name": talent_name,
        "new_level": general["talent_ygzq"] if talent_name == "一鼓作气"
        else general["talent_ygsj"] if talent_name == "勇冠三军"
        else general["talent_djzc"] if talent_name == "大将之材"
        else general["talent_tqtb"],
        "talent_skill": general["talent_skill"],
    }))
    sync_cache_update(general_id, updates)


async def handle_general_dismiss(websocket, client_id, msg):
    """解雇武将（仅未编组状态允许）
    入参: data.general_id - 武将ID
    返回: {general_id, hero_name}
    """
    data = msg.get("data", {})
    general_id = data.get("general_id")

    if not general_id:
        await send_message(websocket, make_response("error", "缺少武将ID", ""))
        return

    general = await get_general_by_id(general_id)
    if general is None:
        await send_message(websocket, make_response("error", "武将不存在", ""))
        return

    if general.get("status") != 0:
        await send_message(websocket, make_response("error", "武将当前状态不允许解雇", ""))
        return

    hero_name = general.get("hero_name", "")
    user_id = general.get("user_id", "")

    player_name = (user_resource_cache.get(user_id, {}) or {}).get("player_name", "")
    if hero_name == player_name:
        await send_message(websocket, make_response("error", "同名武将不允许解雇", ""))
        return

    await delete_general(general_id)
    sync_cache_delete(user_id, general_id)

    await send_message(websocket, make_response("success", "解雇成功", {
        "general_id": general_id,
        "hero_name": hero_name,
    }))