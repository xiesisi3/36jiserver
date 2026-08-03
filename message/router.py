import json
import logging

from core.connection import unregister_client, send_message
from message.protocol import decode, make_response, set_current_msg_type
from message.handlers import handle_echo, handle_broadcast_request, handle_private_message
from system_user.system_user_interface import handle_register, handle_login
from towns.towns_interface import handle_towns_all, handle_towns_viewport, handle_towns_detail
from roads.roads_interface import handle_roads_all, handle_roads_by_town
from terrain.terrain_interface import handle_terrain_all
from nations.nations_interface import handle_nations_all, handle_nations_select
from user_resource.user_resource_interface import handle_user_resource, handle_user_exists
from server_timer.server_timer_interface import handle_server_uptime
from general.general_interface import (
    handle_general_list,
    handle_general_detail,
    handle_general_add_exp,
    handle_general_add_attr,
    handle_general_update_status,
    handle_general_talent_upgrade,
    handle_general_dismiss,
)
from towns.towns_inner.towns_inner_recruit import (
    handle_recruit_copper_quota,
    handle_recruit_pre,
    handle_recruit_confirm,
)
from towns.towns_inner.towns_inner_robber import handle_robber_fight, handle_robber_quota
from towns.towns_inner.towns_inner_market import handle_market_exchange
from notification.notification_interface import (
    handle_message_list,
    handle_message_detail,
    handle_message_mark_read,
    handle_message_delete,
    handle_message_unread_count,
    handle_friend_request,
    handle_friend_accept,
    handle_friend_reject,
    handle_friend_list,
    handle_friend_delete,
    handle_friend_message,
)
from fief.fief_interface import (
    handle_fief_initial_info,
    handle_fief_initial_select,
    handle_fief_create,
    handle_fief_list,
    handle_fief_detail,
    handle_fief_detail_by_town,
    handle_fief_building_detail,
    handle_fief_build,
    handle_fief_upgrade,
    handle_fief_cancel_build,
    handle_fief_demolish,
    handle_fief_upgrade_all_same,
    handle_fief_unlock_grid,
    handle_fief_train_troop,
    handle_fief_train_troop_all,
    handle_fief_train_speedup,
    handle_fief_abandon,
    handle_fief_buildable_list,
    handle_fief_income,
    handle_fief_rename,
)
from troop.troop_interface import (
    handle_troop_list,
    handle_troop_create,
    handle_troop_dismiss,
    handle_troop_detail,
    handle_troop_move,
    handle_troop_update,
    handle_troop_swap,
)
from troop.troop_march_core import (
    handle_march_targets,
    handle_march_preview,
    handle_march_dispatch,
)
from towns.towns_outer.town_outer_grid_interface import (
    handle_outer_grid_info,
    handle_town_troop_list,
)
from treasure.treasure_interface import (
    handle_treasure_list,
    handle_treasure_equip,
    handle_treasure_unequip,
    handle_treasure_enhance,
    handle_treasure_decompose,
    handle_treasure_reset,
    handle_treasure_enhance_quota,
    handle_treasure_material_buy,
    handle_treasure_star_upgrade,
)
from items.item_interface import handle_item_list, handle_item_use
from mission.mission_interface import handle_mission_list, handle_mission_claim, handle_mission_detail
from tech.tech_interface import handle_tech_list, handle_tech_detail, handle_tech_unlock
from legion.legion_interface import (
    handle_legion_list,
    handle_legion_create,
    handle_legion_apply,
    handle_legion_application_handle,
    handle_legion_set_vice,
    handle_legion_transfer,
    handle_legion_leave,
    handle_legion_detail,
    handle_legion_supply,
    handle_legion_granary_supply,
    handle_legion_unlock,
    handle_legion_exchange,
    handle_legion_exchange_list,
    handle_pearl_use,
    handle_legion_stage_list,
    handle_legion_stage_detail,
)

logger = logging.getLogger('36ji-server')

HANDLERS = {
    "echo": handle_echo,
    "broadcast": handle_broadcast_request,
    "private": handle_private_message,
    "register": handle_register,
    "login": handle_login,
    "towns_all": handle_towns_all,
    "towns_viewport": handle_towns_viewport,
    "towns_detail": handle_towns_detail,
    "roads_all": handle_roads_all,
    "roads_by_town": handle_roads_by_town,
    "terrain_all": handle_terrain_all,
    "nations_all": handle_nations_all,
    "nations_select": handle_nations_select,
    "user_resource": handle_user_resource,
    "user_exists": handle_user_exists,
    "server_uptime": handle_server_uptime,
    "general_list": handle_general_list,
    "general_detail": handle_general_detail,
    "recruit_copper_quota": handle_recruit_copper_quota,
    "recruit_pre": handle_recruit_pre,
    "recruit_confirm": handle_recruit_confirm,
    "robber_quota": handle_robber_quota,
    "robber_fight": handle_robber_fight,
    "market_exchange": handle_market_exchange,
    "general_add_exp": handle_general_add_exp,
    "general_add_attr": handle_general_add_attr,
    "general_update_status": handle_general_update_status,
    "general_talent_upgrade": handle_general_talent_upgrade,
    "general_dismiss": handle_general_dismiss,
    "message_list": handle_message_list,
    "message_detail": handle_message_detail,
    "message_mark_read": handle_message_mark_read,
    "message_delete": handle_message_delete,
    "message_unread_count": handle_message_unread_count,
    "friend_request": handle_friend_request,
    "friend_accept": handle_friend_accept,
    "friend_reject": handle_friend_reject,
    "friend_list": handle_friend_list,
    "friend_delete": handle_friend_delete,
    "friend_message": handle_friend_message,
    "fief_initial_info": handle_fief_initial_info,
    "fief_initial_select": handle_fief_initial_select,
    "fief_create": handle_fief_create,
    "fief_list": handle_fief_list,
    "fief_detail": handle_fief_detail,
    "fief_detail_by_town": handle_fief_detail_by_town,
    "fief_building_detail": handle_fief_building_detail,
    "fief_build": handle_fief_build,
    "fief_upgrade": handle_fief_upgrade,
    "fief_cancel_build": handle_fief_cancel_build,
    "fief_demolish": handle_fief_demolish,
    "fief_upgrade_all_same": handle_fief_upgrade_all_same,
    "fief_unlock_grid": handle_fief_unlock_grid,
    "fief_train_troop": handle_fief_train_troop,
    "fief_train_troop_all": handle_fief_train_troop_all,
    "fief_train_speedup": handle_fief_train_speedup,
    "fief_abandon": handle_fief_abandon,
    "fief_buildable_list": handle_fief_buildable_list,
    "fief_income": handle_fief_income,
    "fief_rename": handle_fief_rename,
    "troop_list": handle_troop_list,
    "troop_create": handle_troop_create,
    "troop_dismiss": handle_troop_dismiss,
    "troop_detail": handle_troop_detail,
    "troop_move": handle_troop_move,
    "troop_update": handle_troop_update,
    "troop_swap": handle_troop_swap,
    "march_targets": handle_march_targets,
    "march_preview": handle_march_preview,
    "march_dispatch": handle_march_dispatch,
    "outer_grid_info": handle_outer_grid_info,
    "town_troop_list": handle_town_troop_list,
    "treasure_list": handle_treasure_list,
    "treasure_equip": handle_treasure_equip,
    "treasure_unequip": handle_treasure_unequip,
    "treasure_enhance": handle_treasure_enhance,
    "treasure_decompose": handle_treasure_decompose,
    "treasure_reset": handle_treasure_reset,
    "treasure_enhance_quota": handle_treasure_enhance_quota,
    "treasure_material_buy": handle_treasure_material_buy,
    "treasure_star_upgrade": handle_treasure_star_upgrade,
    "item_list": handle_item_list,
    "item_use": handle_item_use,
    "mission_list": handle_mission_list,
    "mission_claim": handle_mission_claim,
    "mission_detail": handle_mission_detail,
    "tech_list": handle_tech_list,
    "tech_detail": handle_tech_detail,
    "tech_unlock": handle_tech_unlock,
    "legion_list": handle_legion_list,
    "legion_create": handle_legion_create,
    "legion_apply": handle_legion_apply,
    "legion_application_handle": handle_legion_application_handle,
    "legion_set_vice": handle_legion_set_vice,
    "legion_transfer": handle_legion_transfer,
    "legion_leave": handle_legion_leave,
    "legion_detail": handle_legion_detail,
    "legion_supply": handle_legion_supply,
    "legion_granary_supply": handle_legion_granary_supply,
    "legion_unlock": handle_legion_unlock,
    "legion_exchange": handle_legion_exchange,
    "legion_exchange_list": handle_legion_exchange_list,
    "pearl_use": handle_pearl_use,
    "legion_stage_list": handle_legion_stage_list,
    "legion_stage_detail": handle_legion_stage_detail,
}


async def message_handler(websocket, client_id):
    try:
        async for raw_message in websocket:
            try:
                msg = decode(raw_message)
            except json.JSONDecodeError:
                set_current_msg_type(None)
                await send_message(websocket, make_response("error", "消息格式错误，需为 JSON", ""))
                continue
            msg_type = msg.get("type", "")
            set_current_msg_type(msg_type)
            handler = HANDLERS.get(msg_type)
            if handler is None:
                await send_message(websocket, make_response("error", f"未知的消息类型: {msg_type}", ""))
                continue
            try:
                await handler(websocket, client_id, msg)
            except Exception as e:
                logger.error(f"处理消息异常 ({client_id}): {e}")
                await send_message(websocket, make_response("error", "服务器内部错误", ""))
    except Exception as e:
        logger.error(f"连接异常 ({client_id}): {e}")
    finally:
        await unregister_client(client_id)