from core.connection import send_message
from message.protocol import make_response
from nations.nation_core import get_all_nations_from_cache, select_nation


async def handle_nations_all(websocket, client_id, msg):
    nations = get_all_nations_from_cache()
    await send_message(websocket, make_response("success", "国家列表", nations))


async def handle_nations_select(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = (data.get("user_id") or "").strip()
    nation_id = data.get("nation_id")
    player_name = (data.get("player_name") or "").strip()
    personality = (data.get("personality") or "").strip()

    if not user_id:
        await send_message(websocket, make_response("error", "缺少用户ID", ""))
        return

    if not nation_id:
        await send_message(websocket, make_response("error", "缺少国家ID", ""))
        return

    if not player_name:
        await send_message(websocket, make_response("error", "缺少游戏名称", ""))
        return

    if not personality:
        await send_message(websocket, make_response("error", "请选择性格", ""))
        return

    success, result = await select_nation(user_id, nation_id, player_name, personality)
    if success:
        await send_message(websocket, make_response("success", "选择国家成功", {
            "nation_id": nation_id,
            "player_name": player_name,
            "personality": personality,
        }))
    else:
        await send_message(websocket, make_response("error", result, ""))