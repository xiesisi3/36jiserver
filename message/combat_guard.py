"""战斗状态拦截装饰器

城池进入战斗(status != 0)时，禁止对该城池进行写操作（封地、外城、内城）。
"""

import logging
from functools import wraps

from core.connection import send_message
from message.protocol import make_response

logger = logging.getLogger("36ji-server")


def require_town_peace(handler):
    """装饰器：检查目标城池是否处于和平状态
    自动从 msg["data"] 中提取 fief_id / town_id / troop_id，
    查找对应的城池，若 status != 0 则返回错误。
    """

    @wraps(handler)
    async def wrapper(websocket, client_id, msg):
        data = msg.get("data", {})
        town_id = None

        fief_id = data.get("fief_id")
        if fief_id:
            from data.global_data import fief_cache
            fief = fief_cache.get(fief_id)
            if fief:
                town_id = fief.get("town_id")

        if town_id is None:
            town_id = data.get("town_id") or data.get("source_town_id")

        if town_id is None:
            troop_id = data.get("troop_id") or data.get("troop_id_a")
            if troop_id:
                from data.global_data import troop_cache
                troop = troop_cache.get(troop_id)
                if troop:
                    town_id = troop.get("pos")

        if town_id is not None:
            from data.global_data import towns_cache
            town = towns_cache.get(town_id)
            if town and town.get("status", 0) != 0:
                await send_message(websocket, make_response("error", "城池战斗中，无法操作", ""))
                return

        return await handler(websocket, client_id, msg)

    return wrapper