from core.connection import broadcast
from message.protocol import make_response


async def handle_broadcast_request(websocket, client_id, msg):
    await broadcast(make_response("success", "server broadcast", msg.get("data", "")))