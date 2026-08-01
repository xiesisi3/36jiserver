from core.connection import send_message
from message.protocol import make_response
from server_timer.server_timer_core import get_uptime_ms, get_cycle_count, get_last_start_time


async def handle_server_uptime(websocket, client_id, msg):
    await send_message(websocket, make_response("success", "服务器运行时长", {
        "uptime_ms": get_uptime_ms(),
        "cycle_count": get_cycle_count(),
        "last_start_time": get_last_start_time(),
    }))