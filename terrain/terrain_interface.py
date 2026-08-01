from core.connection import send_message
from message.protocol import make_response
from terrain.terrain_core import get_all_terrain_from_cache


async def handle_terrain_all(websocket, client_id, msg):
    data = get_all_terrain_from_cache()
    await send_message(websocket, make_response("success", "地形数据", data))