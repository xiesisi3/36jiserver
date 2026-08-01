from core.connection import send_message
from message.protocol import make_response


async def handle_echo(websocket, client_id, msg):
    await send_message(websocket, make_response("success", "echo reply", msg.get("data", "")))