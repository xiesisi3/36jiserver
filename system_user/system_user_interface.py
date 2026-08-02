from core.connection import send_message, bind_user, kick_old_client
from message.protocol import make_response
from system_user.system_user_core import verify_credentials, register_user
from system_log.system_log_core import record_login_log, record_register_log
from user_resource.user_resource_core import create_user_resource
from data.global_data import user_resource_cache, fief_cache, user_nation_cache


async def handle_register(websocket, client_id, msg):
    data = msg.get("data", {})
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    phone = (data.get("phone") or "").strip()

    if not username or not password:
        await send_message(websocket, make_response("error", "用户名和密码不能为空", ""))
        return

    success, result = await register_user(username, password, phone)
    if success:
        await create_user_resource(result["id"])
        await send_message(websocket, make_response("success", "注册成功", {
            "id": result["id"],
            "username": result["username"],
        }))
        await record_register_log(result["id"], True)
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_login(websocket, client_id, msg):
    data = msg.get("data", {})
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not password:
        await send_message(websocket, make_response("error", "用户名和密码不能为空", ""))
        return

    valid, user = verify_credentials(username, password)
    if valid:
        resource = user_resource_cache.get(user["id"])
        first_login = False
        if resource is None or not resource.get("player_name"):
            first_login = True

        nation_id = user_nation_cache.get(user["id"])
        has_fief = any(f["user_id"] == user["id"] for f in fief_cache.values())

        await send_message(websocket, make_response("success", "登录成功", {
            "id": user["id"],
            "username": user["username"],
            "first_login": first_login,
            "nation_id": nation_id,
            "has_fief": has_fief,
        }))
        await kick_old_client(user["id"])
        bind_user(client_id, user["id"])
        await record_login_log(user["id"], True)
    else:
        await send_message(websocket, make_response("error", "用户名或密码错误", ""))
        if user is not None:
            await record_login_log(user["id"], False)