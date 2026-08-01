from core.connection import send_message
from message.protocol import make_response
from roads.roads_core import (
    get_all_roads_from_cache,
    get_roads_by_town_from_cache,
)


async def handle_roads_all(websocket, client_id, msg):
    roads = get_all_roads_from_cache()
    await send_message(websocket, make_response("success", "道路列表", roads))


async def handle_roads_by_town(websocket, client_id, msg):
    data = msg.get("data", {})
    town_id = data.get("town_id")
    if not town_id:
        await send_message(websocket, make_response("error", "缺少城池ID", ""))
        return
    roads = get_roads_by_town_from_cache(town_id)
    await send_message(websocket, make_response("success", "城池道路", roads))