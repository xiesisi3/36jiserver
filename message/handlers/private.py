import logging

from core.connection import send_message
from data.global_data import clients
from message.protocol import make_response

logger = logging.getLogger('36ji-server')


async def handle_private_message(websocket, client_id, msg):
    target_id = msg.get("target")
    data = msg.get("data", "")
    if not target_id:
        await send_message(websocket, make_response("error", "缺少目标客户端 ID", ""))
        return
    if target_id not in clients:
        await send_message(websocket, make_response("error", "目标客户端不在线", ""))
        return
    await send_message(clients[target_id], make_response("success", f"来自 {client_id} 的私信", data))
    logger.info(f"私信: {client_id} -> {target_id}: {data}")