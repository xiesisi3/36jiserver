import logging
from core.connection import broadcast
from message.protocol import make_response

logger = logging.getLogger("36ji-server")


async def broadcast_combat_state(town_id, state, extra_data=None):
    data = {
        "type": "town_combat_notify",
        "town_id": town_id,
        "state": state,
    }
    if extra_data:
        data.update(extra_data)
    await broadcast(make_response("success", "城池战斗状态通知", data))