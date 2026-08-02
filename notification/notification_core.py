"""消息/好友 核心逻辑"""
import logging

from notification.notification_db import (
    insert_message,
    get_message_by_id,
    insert_friend,
    get_friend_relation,
    get_friend_by_id,
    update_friend_status,
    delete_friend,
)
from core.connection import send_to_user, is_user_online
from message.protocol import make_response

logger = logging.getLogger('36ji-server')


async def publish_system_message(receiver_id, receiver_name, title, content, category=None,
                                  msg_type=1, sender_id=None, extra=None):
    """服务端给指定用户发送消息（持久化）
    :param receiver_id: 接收方ID
    :param receiver_name: 接收方名称
    :param title: 消息标题
    :param content: 消息正文
    :param category: 分类标签（战斗/城池/外交/活动/公告/系统）
    :param msg_type: 消息类型 1=系统消息 2=好友申请 3=好友私聊 4=申请结果 5=军团申请
    :param sender_id: 发送方ID，None表示系统发送
    :param extra: 扩展数据（军团申请: {"legion_id": 1, "replied": 0}）
    :return: 消息ID
    """
    import json
    data = {
        "sender_id": sender_id,
        "sender_name": "系统" if sender_id is None else None,
        "receiver_id": receiver_id,
        "receiver_name": receiver_name,
        "title": title,
        "content": content,
        "category": category,
        "msg_type": msg_type,
        "extra_data": json.dumps(extra, ensure_ascii=False) if extra else None,
        "is_read": 0,
        "sender_deleted": 0,
        "receiver_deleted": 0,
    }
    message_id = await insert_message(data)
    logger.info(f"系统消息已发送: receiver={receiver_id}, title={title}, msg_id={message_id}")
    return message_id


async def send_friend_request(sender_id, sender_name, receiver_id, receiver_name, remark=None):
    """三类消息：发送好友申请
    :param sender_id: 申请方ID
    :param sender_name: 申请方名称
    :param receiver_id: 目标方ID
    :param receiver_name: 目标方名称
    :param remark: 申请附言
    :return: (success, message)
    """
    if sender_id == receiver_id:
        return False, "不能添加自己为好友"

    existing = await get_friend_relation(sender_id, receiver_id)
    if existing:
        if existing["status"] == 0:
            return False, "已存在待处理的好友申请"
        elif existing["status"] == 1:
            return False, "已经是好友"
        elif existing["status"] == 2:
            return False, "对方已拒绝，请勿重复申请"

    friend_id = await insert_friend({
        "user_id": sender_id,
        "friend_id": receiver_id,
        "user_name": sender_name,
        "friend_name": receiver_name,
        "remark": remark,
        "status": 0,
    })

    msg_id = await insert_message({
        "sender_id": sender_id,
        "sender_name": sender_name,
        "receiver_id": receiver_id,
        "receiver_name": receiver_name,
        "title": "好友申请",
        "content": f"{sender_name} 申请添加您为好友" + (f"（附言：{remark}）" if remark else ""),
        "category": "好友",
        "msg_type": 2,
        "is_read": 0,
        "sender_deleted": 0,
        "receiver_deleted": 0,
    })

    if is_user_online(receiver_id):
        msg = await get_message_by_id(msg_id)
        if msg:
            await send_to_user(receiver_id, make_response("success", "新好友申请", msg))

    return True, "好友申请已发送"


async def accept_friend_request(user_id, user_name, friend_relation_id):
    """同意好友申请
    :param user_id: 当前用户ID（被申请方）
    :param user_name: 当前用户名称
    :param friend_relation_id: 好友关系ID
    :return: (success, message)
    """
    relation = await get_friend_by_id(friend_relation_id)
    if relation is None:
        return False, "好友申请不存在"

    if relation["status"] != 0:
        return False, "该申请已处理"

    if relation["friend_id"] != user_id:
        return False, "无权处理此申请"

    await update_friend_status(friend_relation_id, 1)

    requester_id = relation["user_id"]
    requester_name = relation["user_name"]
    target_name = relation["friend_name"]

    await insert_message({
        "sender_id": None,
        "sender_name": "系统",
        "receiver_id": requester_id,
        "receiver_name": requester_name,
        "title": "好友申请通过",
        "content": f"{target_name} 已同意您的好友申请",
        "category": "好友",
        "msg_type": 4,
        "is_read": 0,
        "sender_deleted": 0,
        "receiver_deleted": 0,
    })

    if is_user_online(requester_id):
        await send_to_user(requester_id, make_response("success", "好友申请已通过", {
            "friend_name": target_name,
        }))

    return True, "已同意好友申请"


async def reject_friend_request(user_id, friend_relation_id):
    """拒绝好友申请
    :param user_id: 当前用户ID（被申请方）
    :param friend_relation_id: 好友关系ID
    :return: (success, message)
    """
    relation = await get_friend_by_id(friend_relation_id)
    if relation is None:
        return False, "好友申请不存在"

    if relation["status"] != 0:
        return False, "该申请已处理"

    if relation["friend_id"] != user_id:
        return False, "无权处理此申请"

    await update_friend_status(friend_relation_id, 2)
    return True, "已拒绝好友申请"


async def send_friend_message(sender_id, sender_name, receiver_id, receiver_name, content):
    """三类消息：发送好友私聊
    :param sender_id: 发送方ID
    :param sender_name: 发送方名称
    :param receiver_id: 接收方ID
    :param receiver_name: 接收方名称
    :param content: 消息内容
    :return: (success, message, msg_id)
    """
    relation = await get_friend_relation(sender_id, receiver_id)
    if relation is None or relation["status"] != 1:
        return False, "双方不是好友，无法发送消息", None

    msg_id = await insert_message({
        "sender_id": sender_id,
        "sender_name": sender_name,
        "receiver_id": receiver_id,
        "receiver_name": receiver_name,
        "title": None,
        "content": content,
        "category": None,
        "msg_type": 3,
        "is_read": 0,
        "sender_deleted": 0,
        "receiver_deleted": 0,
    })

    if is_user_online(receiver_id):
        msg = await get_message_by_id(msg_id)
        if msg:
            await send_to_user(receiver_id, make_response("success", "新好友消息", msg))

    return True, "消息已发送", msg_id


async def remove_friend(user_id, friend_relation_id):
    """删除好友
    :param user_id: 当前用户ID
    :param friend_relation_id: 好友关系ID
    :return: (success, message)
    """
    relation = await get_friend_by_id(friend_relation_id)
    if relation is None:
        return False, "好友关系不存在"

    if relation["user_id"] != user_id and relation["friend_id"] != user_id:
        return False, "无权删除此好友"

    await delete_friend(friend_relation_id)
    return True, "好友已删除"