"""消息/好友 对外接口"""
import logging
from core.connection import send_message, is_user_online
from message.protocol import make_response
from notification.notification_db import (
    get_messages_by_user,
    get_message_count,
    get_message_by_id,
    get_unread_count,
    mark_message_read,
    batch_mark_read,
    delete_message,
    get_friends_by_user,
)
from notification.notification_core import (
    send_friend_request,
    accept_friend_request,
    reject_friend_request,
    send_friend_message,
    remove_friend,
)

logger = logging.getLogger('36ji-server')


async def handle_message_list(websocket, client_id, msg):
    """获取用户消息列表（分页，自动排除已删除的消息）
    入参: {user_id, msg_type?, limit?, offset?}
    返回: {messages: 消息列表, total: 总条数}
    """
    data = msg.get("data", {})
    user_id = data.get("user_id")
    if not user_id:
        await send_message(websocket, make_response("error", "user_id 不能为空", ""))
        return

    msg_type = data.get("msg_type")
    limit = data.get("limit", 20)
    offset = data.get("offset", 0)
    messages = await get_messages_by_user(user_id, msg_type=msg_type, limit=limit, offset=offset)
    total = await get_message_count(user_id, msg_type=msg_type)
    await send_message(websocket, make_response("success", "消息列表", {"messages": messages, "total": total}))


async def handle_message_detail(websocket, client_id, msg):
    """获取单条消息详情
    入参: {message_id}
    返回: 消息详情
    """
    data = msg.get("data", {})
    message_id = data.get("message_id")
    if not message_id:
        await send_message(websocket, make_response("error", "message_id 不能为空", ""))
        return

    message = await get_message_by_id(message_id)
    if message is None:
        await send_message(websocket, make_response("error", "消息不存在", ""))
        return

    await mark_message_read(message_id)
    await send_message(websocket, make_response("success", "消息详情", message))


async def handle_message_mark_read(websocket, client_id, msg):
    """标记消息已读（支持单条或批量）
    入参: {message_id 或 message_ids(列表)}
    """
    data = msg.get("data", {})
    message_id = data.get("message_id")
    message_ids = data.get("message_ids")

    if message_id:
        await mark_message_read(message_id)
    elif message_ids and isinstance(message_ids, list):
        await batch_mark_read(message_ids)
    else:
        await send_message(websocket, make_response("error", "请提供 message_id 或 message_ids", ""))
        return
    await send_message(websocket, make_response("success", "已标记已读", ""))


async def handle_message_delete(websocket, client_id, msg):
    """删除消息（P2P消息双删逻辑 / 系统消息直接删除）
    入参: {user_id, message_id}
    """
    data = msg.get("data", {})
    user_id = data.get("user_id")
    message_id = data.get("message_id")
    if not user_id or not message_id:
        await send_message(websocket, make_response("error", "user_id 和 message_id 不能为空", ""))
        return

    result = await delete_message(message_id, user_id)
    if result == "not_found":
        await send_message(websocket, make_response("error", "消息不存在", ""))
    else:
        await send_message(websocket, make_response("success", "消息已删除", ""))


async def handle_message_unread_count(websocket, client_id, msg):
    """获取用户未读消息数量
    入参: {user_id}
    返回: {count}
    """
    data = msg.get("data", {})
    user_id = data.get("user_id")
    if not user_id:
        await send_message(websocket, make_response("error", "user_id 不能为空", ""))
        return

    count = await get_unread_count(user_id)
    await send_message(websocket, make_response("success", "未读消息数量", {"count": count}))


async def handle_friend_request(websocket, client_id, msg):
    """发送好友申请
    入参: {sender_id, sender_name, receiver_id, receiver_name, remark?}
    返回: 申请结果
    """
    data = msg.get("data", {})
    sender_id = data.get("sender_id")
    sender_name = data.get("sender_name")
    receiver_id = data.get("receiver_id")
    receiver_name = data.get("receiver_name")
    remark = data.get("remark")

    if not sender_id or not sender_name or not receiver_id or not receiver_name:
        await send_message(websocket, make_response("error", "参数不完整", ""))
        return

    success, message = await send_friend_request(sender_id, sender_name, receiver_id, receiver_name, remark)
    if success:
        await send_message(websocket, make_response("success", message, ""))
    else:
        await send_message(websocket, make_response("error", message, ""))


async def handle_friend_accept(websocket, client_id, msg):
    """同意好友申请
    入参: {user_id, user_name, friend_id(好友关系ID)}
    返回: 处理结果
    """
    data = msg.get("data", {})
    user_id = data.get("user_id")
    user_name = data.get("user_name")
    friend_id = data.get("friend_id")

    if not user_id or not user_name or not friend_id:
        await send_message(websocket, make_response("error", "参数不完整", ""))
        return

    success, message = await accept_friend_request(user_id, user_name, friend_id)
    if success:
        await send_message(websocket, make_response("success", message, ""))
    else:
        await send_message(websocket, make_response("error", message, ""))


async def handle_friend_reject(websocket, client_id, msg):
    """拒绝好友申请
    入参: {user_id, friend_id(好友关系ID)}
    返回: 处理结果
    """
    data = msg.get("data", {})
    user_id = data.get("user_id")
    friend_id = data.get("friend_id")

    if not user_id or not friend_id:
        await send_message(websocket, make_response("error", "参数不完整", ""))
        return

    success, message = await reject_friend_request(user_id, friend_id)
    if success:
        await send_message(websocket, make_response("success", message, ""))
    else:
        await send_message(websocket, make_response("error", message, ""))


async def handle_friend_list(websocket, client_id, msg):
    """获取好友列表（含在线状态）
    入参: {user_id}
    返回: 好友列表，每项含 online 字段
    """
    data = msg.get("data", {})
    user_id = data.get("user_id")
    if not user_id:
        await send_message(websocket, make_response("error", "user_id 不能为空", ""))
        return

    friends = await get_friends_by_user(user_id)
    result = []
    for f in friends:
        friend_data = dict(f)
        if f["user_id"] == user_id:
            friend_data["friend_user_id"] = f["friend_id"]
            friend_data["friend_user_name"] = f["friend_name"]
        else:
            friend_data["friend_user_id"] = f["user_id"]
            friend_data["friend_user_name"] = f["user_name"]
        friend_data["online"] = is_user_online(friend_data["friend_user_id"])
        result.append(friend_data)
    await send_message(websocket, make_response("success", "好友列表", result))


async def handle_friend_delete(websocket, client_id, msg):
    """删除好友
    入参: {user_id, friend_id(好友关系ID)}
    返回: 处理结果
    """
    data = msg.get("data", {})
    user_id = data.get("user_id")
    friend_id = data.get("friend_id")

    if not user_id or not friend_id:
        await send_message(websocket, make_response("error", "参数不完整", ""))
        return

    success, message = await remove_friend(user_id, friend_id)
    if success:
        await send_message(websocket, make_response("success", message, ""))
    else:
        await send_message(websocket, make_response("error", message, ""))


async def handle_friend_message(websocket, client_id, msg):
    """发送好友私聊消息
    入参: {sender_id, sender_name, receiver_id, receiver_name, content}
    返回: 发送结果
    """
    data = msg.get("data", {})
    sender_id = data.get("sender_id")
    sender_name = data.get("sender_name")
    receiver_id = data.get("receiver_id")
    receiver_name = data.get("receiver_name")
    content = data.get("content")

    if not sender_id or not sender_name or not receiver_id or not receiver_name or not content:
        await send_message(websocket, make_response("error", "参数不完整", ""))
        return

    success, message, msg_id = await send_friend_message(sender_id, sender_name, receiver_id, receiver_name, content)
    if success:
        await send_message(websocket, make_response("success", message, {"message_id": msg_id}))
    else:
        await send_message(websocket, make_response("error", message, ""))