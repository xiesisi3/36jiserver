"""一类消息：服务端主动广播，不持久化，仅在线客户端可见"""
import logging

from core.connection import broadcast
from message.protocol import make_response

logger = logging.getLogger('36ji-server')


async def publish_system_broadcast(event_type, data):
    """服务端主动广播系统事件给所有在线客户端
    适用场景：城池进入战斗、国家事件、全服公告等
    :param event_type: 事件类型标识（如 "town_battle_start"）
    :param data: 事件数据字典
    """
    await broadcast(make_response("success", event_type, data))
    logger.info(f"系统广播: event_type={event_type}")