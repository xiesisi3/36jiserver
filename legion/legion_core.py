import json
import logging
import aiomysql
from data.global_data import (
    legion_cache, legion_member_cache, legion_member_index,
    user_resource_cache, user_nation_cache, troop_cache,
    fief_cache, towns_cache, fief_item_effects_cache,
)
from legion.legion_db import (
    create_tables, get_all_legions, get_legion_by_id, get_legion_by_name,
    insert_legion, update_legion_field,
    get_all_legion_members, get_member_by_user, get_members_by_legion,
    insert_legion_member, update_member_role, update_member_field, delete_member,
    get_application, upsert_application, update_application_status, get_pending_applications,
    get_all_fief_item_effects, get_fief_item_effect, upsert_fief_item_effect, delete_fief_item_effect,
)
from notification.notification_core import publish_system_message
from notification.notification_db import mark_application_replied
from user_resource.user_resource_db import update_user_resource_field
from core.connection import send_to_user
from core.database import get_pool
from troop.troop_utils import calculate_max_carry_food
from server_timer.server_timer_core import get_uptime_ms
from data.legion_exchange_config import (
    GRANARY_STAGES, CHEST_TICKET_STAGES, BUFF_STAGES, SPECIAL_STAGES,
    SKILL_BOOK_LIST, SKILL_BOOK_PRICE,
    PEARL_CONFIG, PEARL_MAX_TOWN_LEVEL,
    get_granary_stage_cost, get_granary_stage_max,
    get_chest_ticket_stage_cost, get_buff_stage_cost, get_special_stage_cost,
    get_item_price, get_item_unlock_stage, get_all_unlockable_items,
)
from items.item_core import add_item_to_user

logger = logging.getLogger('36ji-server')

ROLE_LEADER = 1
ROLE_VICE = 2
ROLE_MEMBER = 3

LEGION_CREATE_COST = 1000


async def init_legions():
    await create_tables()

    rows = await get_all_legions()
    legion_cache.clear()
    for row in rows:
        legion_cache[row["id"]] = dict(row)

    members = await get_all_legion_members()
    legion_member_cache.clear()
    legion_member_index.clear()
    for m in members:
        legion_member_cache[m["user_id"]] = dict(m)
        lid = m["legion_id"]
        if lid not in legion_member_index:
            legion_member_index[lid] = set()
        legion_member_index[lid].add(m["user_id"])

    # 加载封地灵珠效果到全局缓存
    effects = await get_all_fief_item_effects()
    fief_item_effects_cache.clear()
    for e in effects:
        fief_item_effects_cache[(e["user_id"], e["town_id"])] = float(e["bonus"])

    logger.info(f"军团模块初始化完成: {len(legion_cache)} 个军团, {len(legion_member_cache)} 个成员, "
                f"{len(fief_item_effects_cache)} 个灵珠效果")


def _get_leader_user_id(legion_id):
    """获取军团长的user_id"""
    for uid, m in legion_member_cache.items():
        if m["legion_id"] == legion_id and m["role"] == ROLE_LEADER:
            return uid
    return None


def _get_legion_member_count(legion_id):
    """获取军团成员数量"""
    return len(legion_member_index.get(legion_id, set()))


def _build_legion_detail(legion_id):
    """构建军团详情数据"""
    legion = legion_cache.get(legion_id)
    if not legion:
        return None

    members = []
    for uid in legion_member_index.get(legion_id, set()):
        m = legion_member_cache.get(uid)
        if m:
            player_name = (user_resource_cache.get(uid, {}) or {}).get("player_name", "")
            role_map = {ROLE_LEADER: "军团长", ROLE_VICE: "副军团长", ROLE_MEMBER: "普通成员"}
            members.append({
                "user_id": uid,
                "player_name": player_name,
                "role": m["role"],
                "role_name": role_map.get(m["role"], ""),
                "personal_granary": m["personal_granary"],
                "personal_total_score": m["personal_total_score"],
                "personal_current_score": m["personal_current_score"],
                "join_time": str(m["join_time"]) if m.get("join_time") else "",
            })

    members.sort(key=lambda x: (x["role"], x["join_time"]))

    return {
        "id": legion["id"],
        "nation_id": legion["nation_id"],
        "name": legion["name"],
        "description": legion["description"],
        "total_combat_score": legion["total_combat_score"],
        "available_combat_score": legion["available_combat_score"],
        "granary_max": legion["granary_max"],
        "granary_current": legion["granary_current"],
        "granary_stage": legion.get("granary_stage", 0),
        "chest_ticket_stage": legion.get("chest_ticket_stage", 0),
        "buff_stage": legion.get("buff_stage", 0),
        "special_stage": legion.get("special_stage", 0),
        "member_count": len(members),
        "create_time": str(legion["create_time"]) if legion.get("create_time") else "",
        "members": members,
    }


# ==================== 军团列表 ====================


def get_legions_by_nation(nation_id):
    result = []
    for lid, legion in legion_cache.items():
        if legion["nation_id"] == nation_id:
            detail = _build_legion_detail(lid)
            if detail:
                result.append(detail)
    return result


# ==================== 创建军团 ====================


async def create_legion(user_id, nation_id, name, description):
    if user_id not in user_resource_cache:
        return False, "用户资源不存在"

    if user_id in legion_member_cache:
        return False, "你已加入军团，无法创建"

    if user_nation_cache.get(user_id) != nation_id:
        return False, "只能创建本国军团"

    existing = await get_legion_by_name(name)
    if existing:
        return False, "军团名称已存在"

    resource = user_resource_cache[user_id]
    if resource.get("copper", 0) < LEGION_CREATE_COST:
        return False, f"铜币不足，需要{LEGION_CREATE_COST}，当前{resource.get('copper', 0)}"

    new_copper = resource["copper"] - LEGION_CREATE_COST
    await update_user_resource_field(user_id, "copper", new_copper)
    resource["copper"] = new_copper

    legion_id = await insert_legion({
        "nation_id": nation_id,
        "name": name,
        "description": description,
    })

    legion_cache[legion_id] = {
        "id": legion_id,
        "nation_id": nation_id,
        "name": name,
        "description": description,
        "total_combat_score": 0,
        "available_combat_score": 0,
        "granary_max": 100000,
        "granary_current": 0,
    }

    await insert_legion_member({
        "legion_id": legion_id,
        "user_id": user_id,
        "role": ROLE_LEADER,
    })

    legion_member_cache[user_id] = {
        "legion_id": legion_id,
        "user_id": user_id,
        "role": ROLE_LEADER,
        "personal_granary": 0,
        "personal_total_score": 0,
        "personal_current_score": 0,
    }
    if legion_id not in legion_member_index:
        legion_member_index[legion_id] = set()
    legion_member_index[legion_id].add(user_id)

    player_name = (user_resource_cache.get(user_id, {}) or {}).get("player_name", "")
    logger.info(f"军团创建成功: {name}({legion_id}), 军团长={player_name}({user_id}), 消耗铜币{LEGION_CREATE_COST}")

    return True, {
        "legion_id": legion_id,
        "name": name,
        "copper_remaining": new_copper,
    }


# ==================== 申请加入军团 ====================


async def apply_join_legion(user_id, legion_id):
    legion = legion_cache.get(legion_id)
    if legion is None:
        return False, "军团不存在"

    if user_id in legion_member_cache:
        return False, "你已加入军团"

    if user_nation_cache.get(user_id) != legion["nation_id"]:
        return False, "只能加入本国军团"

    existing = await get_application(legion_id, user_id)
    if existing and existing["status"] == 0:
        return False, "已有待处理的申请，请等待军团长回复"

    leader_user_id = _get_leader_user_id(legion_id)
    if leader_user_id is None:
        return False, "军团没有军团长"

    await upsert_application(legion_id, user_id, 0)

    player_name = (user_resource_cache.get(user_id, {}) or {}).get("player_name", "")
    leader_name = (user_resource_cache.get(leader_user_id, {}) or {}).get("player_name", "")

    await publish_system_message(
        receiver_id=leader_user_id,
        receiver_name=leader_name,
        title="军团申请",
        content=f"玩家 【{player_name}】 申请加入你的军团【{legion['name']}】",
        category="军团",
        msg_type=5,
        sender_id=user_id,
        extra={"legion_id": legion_id, "replied": 0},
    )

    logger.info(f"军团申请: {player_name}({user_id}) → {legion['name']}({legion_id})")
    return True, "申请已发送"


# ==================== 处理申请（同意/拒绝） ====================


async def handle_application(leader_user_id, application_user_id, legion_id, accept):
    leader_member = legion_member_cache.get(leader_user_id)
    if leader_member is None or leader_member["role"] != ROLE_LEADER:
        return False, "你不是军团长，无权处理申请"

    if leader_member["legion_id"] != legion_id:
        return False, "申请不属于你的军团"

    existing = await get_application(legion_id, application_user_id)
    if existing is None or existing["status"] != 0:
        return False, "申请不存在或已处理"

    if accept:
        if application_user_id in legion_member_cache:
            return False, "该玩家已加入军团"

        await update_application_status(legion_id, application_user_id, 1)

        await mark_application_replied(leader_user_id, application_user_id)

        await insert_legion_member({
            "legion_id": legion_id,
            "user_id": application_user_id,
            "role": ROLE_MEMBER,
        })

        legion_member_cache[application_user_id] = {
            "legion_id": legion_id,
            "user_id": application_user_id,
            "role": ROLE_MEMBER,
            "personal_granary": 0,
            "personal_total_score": 0,
            "personal_current_score": 0,
        }
        legion_member_index[legion_id].add(application_user_id)

        player_name = (user_resource_cache.get(application_user_id, {}) or {}).get("player_name", "")
        legion_name = legion_cache[legion_id]["name"]

        await publish_system_message(
            receiver_id=application_user_id,
            receiver_name=player_name,
            title="军团申请结果",
            content=f"你申请加入军团【{legion_name}】已通过",
            category="军团",
            msg_type=4,
        )

        # 玩家在线则实时推送加入军团通知
        await send_to_user(application_user_id, {
            "type": "legion_join",
            "code": 0,
            "data": {
                "legion_id": legion_id,
                "legion_name": legion_name,
                "msg": f"恭喜 【{player_name}】 玩家成功加入军团【{legion_name}】",
            },
        })

        logger.info(f"军团申请通过: {player_name}({application_user_id}) 加入 {legion_name}({legion_id})")
        return True, "已同意申请"
    else:
        await update_application_status(legion_id, application_user_id, 2)

        await mark_application_replied(leader_user_id, application_user_id)

        player_name = (user_resource_cache.get(application_user_id, {}) or {}).get("player_name", "")
        legion_name = legion_cache[legion_id]["name"]

        await publish_system_message(
            receiver_id=application_user_id,
            receiver_name=player_name,
            title="军团申请结果",
            content=f"你申请加入军团【{legion_name}】已被拒绝",
            category="军团",
            msg_type=4,
        )

        logger.info(f"军团申请拒绝: {player_name}({application_user_id}) 被 {legion_name} 拒绝")
        return True, "已拒绝申请"


# ==================== 设置副军团长 ====================


async def set_vice_leader(leader_user_id, target_user_id):
    if leader_user_id == target_user_id:
        return False, "不能对自己操作"

    leader_member = legion_member_cache.get(leader_user_id)
    if leader_member is None or leader_member["role"] != ROLE_LEADER:
        return False, "你不是军团长"

    target_member = legion_member_cache.get(target_user_id)
    if target_member is None:
        return False, "目标玩家不在军团中"

    if target_member["legion_id"] != leader_member["legion_id"]:
        return False, "目标玩家不在你的军团中"

    if target_member["role"] == ROLE_LEADER:
        return False, "目标玩家已是军团长"

    await update_member_role(target_user_id, ROLE_VICE)
    target_member["role"] = ROLE_VICE

    target_name = (user_resource_cache.get(target_user_id, {}) or {}).get("player_name", "")
    legion_name = legion_cache[leader_member["legion_id"]]["name"]
    logger.info(f"副军团长设置: {target_name}({target_user_id}) 成为 {legion_name} 副军团长")

    return True, f"已将 {target_name} 设置为副军团长"


# ==================== 移交军团长 ====================


async def transfer_leader(leader_user_id, target_user_id):
    if leader_user_id == target_user_id:
        return False, "不能移交给自己"

    leader_member = legion_member_cache.get(leader_user_id)
    if leader_member is None or leader_member["role"] != ROLE_LEADER:
        return False, "你不是军团长"

    target_member = legion_member_cache.get(target_user_id)
    if target_member is None:
        return False, "目标玩家不在军团中"

    if target_member["legion_id"] != leader_member["legion_id"]:
        return False, "目标玩家不在你的军团中"

    await update_member_role(leader_user_id, ROLE_MEMBER)
    await update_member_role(target_user_id, ROLE_LEADER)

    leader_member["role"] = ROLE_MEMBER
    target_member["role"] = ROLE_LEADER

    leader_name = (user_resource_cache.get(leader_user_id, {}) or {}).get("player_name", "")
    target_name = (user_resource_cache.get(target_user_id, {}) or {}).get("player_name", "")
    legion_name = legion_cache[leader_member["legion_id"]]["name"]
    logger.info(f"军团长移交: {leader_name} → {target_name}, 军团={legion_name}")

    return True, f"军团长已移交给 {target_name}"


# ==================== 退出军团 ====================


async def leave_legion(user_id):
    member = legion_member_cache.get(user_id)
    if member is None:
        return False, "你不在军团中"

    if member["role"] == ROLE_LEADER:
        return False, "军团长无法主动退出，请先移交军团长职务"

    legion_id = member["legion_id"]
    await delete_member(user_id)

    del legion_member_cache[user_id]
    if legion_id in legion_member_index:
        legion_member_index[legion_id].discard(user_id)

    player_name = (user_resource_cache.get(user_id, {}) or {}).get("player_name", "")
    legion_name = legion_cache.get(legion_id, {}).get("name", "")
    logger.info(f"退出军团: {player_name}({user_id}) 退出 {legion_name}({legion_id})")

    return True, "已退出军团"


# ==================== 军团详情 ====================


def get_legion_detail(legion_id):
    return _build_legion_detail(legion_id)


def get_my_legion_detail(user_id):
    member = legion_member_cache.get(user_id)
    if member is None:
        return None
    return _build_legion_detail(member["legion_id"])


# ==================== 个人粮仓补给部队 ====================


async def supply_from_granary(user_id, troop_id, food_amount):
    """玩家从个人粮仓补给自己的部队（事务保证原子性）"""
    if food_amount <= 0:
        return False, "补给数量必须为正数"

    member = legion_member_cache.get(user_id)
    if member is None:
        return False, "你不在军团中"

    troop = troop_cache.get(troop_id)
    if troop is None:
        return False, "部队不存在"

    if troop["user_id"] != user_id:
        return False, "部队不属于你"

    if troop.get("status") != 1:
        return False, "部队必须处于驻守状态才能补给"

    # 计算部队粮食上限（预检查，事务内会再次校验）
    max_food = calculate_max_carry_food(troop.get("team", []))
    current_food = troop.get("food", 0)
    if current_food + food_amount > max_food:
        return False, f"部队粮食已达上限，当前{current_food}，上限{max_food}，可补给{max_food - current_food}"

    pool = get_pool()
    async with pool.acquire() as txn_conn:
        await txn_conn.begin()
        async with txn_conn.cursor(aiomysql.DictCursor) as cur:
            # 锁定个人粮仓行（FOR UPDATE 保证并发安全）
            await cur.execute(
                "SELECT personal_granary FROM legion_members WHERE user_id = %s FOR UPDATE",
                (user_id,)
            )
            db_member = await cur.fetchone()
            if db_member is None:
                await txn_conn.rollback()
                return False, "不在军团中"

            if db_member["personal_granary"] < food_amount:
                await txn_conn.rollback()
                return False, f"个人粮仓不足，需要{food_amount}，当前{db_member['personal_granary']}"

            # 锁定部队行（FOR UPDATE 保证并发安全）
            await cur.execute(
                "SELECT team, food FROM troops WHERE id = %s FOR UPDATE",
                (troop_id,)
            )
            db_troop = await cur.fetchone()
            if db_troop is None:
                await txn_conn.rollback()
                return False, "部队不存在"

            # 事务内重新计算粮食上限（以DB数据为准）
            db_team = db_troop["team"]
            if isinstance(db_team, str):
                db_team = json.loads(db_team)
            db_max_food = calculate_max_carry_food(db_team)
            db_new_food = db_troop["food"] + food_amount
            if db_new_food > db_max_food:
                await txn_conn.rollback()
                return False, f"部队粮食已达上限，当前{db_troop['food']}，上限{db_max_food}"

            new_granary = db_member["personal_granary"] - food_amount

            await cur.execute(
                "UPDATE legion_members SET personal_granary = %s WHERE user_id = %s",
                (new_granary, user_id)
            )
            await cur.execute(
                "UPDATE troops SET food = %s, update_time = %s WHERE id = %s",
                (db_new_food, get_uptime_ms(), troop_id)
            )

        await txn_conn.commit()

    # 事务成功后更新内存缓存
    member["personal_granary"] = new_granary
    troop["food"] = db_new_food

    logger.info(f"个人粮仓补给: user={user_id}, troop={troop_id}, food={food_amount}, granary={new_granary}, troop_food={db_new_food}")
    return True, {
        "troop_id": troop_id,
        "food_added": food_amount,
        "food_total": db_new_food,
        "personal_granary_remaining": new_granary,
    }


# ==================== 军团粮仓补给部队（军团长/副军团长操作） ====================


async def supply_from_legion_granary(operator_user_id, target_troop_id, food_amount):
    """军团长/副军团长从军团粮仓补给军团内任意成员的部队（事务保证原子性）"""
    if food_amount <= 0:
        return False, "补给数量必须为正数"

    # 校验操作者权限
    operator = legion_member_cache.get(operator_user_id)
    if operator is None:
        return False, "你不在军团中"
    if operator["role"] not in (ROLE_LEADER, ROLE_VICE):
        return False, "只有军团长或副军团长才能操作军团粮仓"

    legion_id = operator["legion_id"]
    legion = legion_cache.get(legion_id)
    if legion is None:
        return False, "军团不存在"

    # 校验目标部队
    troop = troop_cache.get(target_troop_id)
    if troop is None:
        return False, "部队不存在"

    target_user_id = troop["user_id"]
    target_member = legion_member_cache.get(target_user_id)
    if target_member is None or target_member["legion_id"] != legion_id:
        return False, "目标部队不属于你的军团"

    if troop.get("status") != 1:
        return False, "部队必须处于驻守状态才能补给"

    # 预检查：部队粮食上限
    max_food = calculate_max_carry_food(troop.get("team", []))
    current_food = troop.get("food", 0)
    if current_food + food_amount > max_food:
        return False, f"部队粮食已达上限，当前{current_food}，上限{max_food}，可补给{max_food - current_food}"

    pool = get_pool()
    async with pool.acquire() as txn_conn:
        await txn_conn.begin()
        async with txn_conn.cursor(aiomysql.DictCursor) as cur:
            # 锁定军团粮仓行（FOR UPDATE 保证并发安全）
            await cur.execute(
                "SELECT granary_current FROM legions WHERE id = %s FOR UPDATE",
                (legion_id,)
            )
            db_legion = await cur.fetchone()
            if db_legion is None:
                await txn_conn.rollback()
                return False, "军团不存在"

            if db_legion["granary_current"] < food_amount:
                await txn_conn.rollback()
                return False, f"军团粮仓不足，需要{food_amount}，当前{db_legion['granary_current']}"

            # 锁定部队行（FOR UPDATE 保证并发安全）
            await cur.execute(
                "SELECT team, food FROM troops WHERE id = %s FOR UPDATE",
                (target_troop_id,)
            )
            db_troop = await cur.fetchone()
            if db_troop is None:
                await txn_conn.rollback()
                return False, "部队不存在"

            # 事务内重新计算粮食上限（以DB数据为准）
            db_team = db_troop["team"]
            if isinstance(db_team, str):
                db_team = json.loads(db_team)
            db_max_food = calculate_max_carry_food(db_team)
            db_new_food = db_troop["food"] + food_amount
            if db_new_food > db_max_food:
                await txn_conn.rollback()
                return False, f"部队粮食已达上限，当前{db_troop['food']}，上限{db_max_food}"

            new_granary = db_legion["granary_current"] - food_amount

            await cur.execute(
                "UPDATE legions SET granary_current = %s WHERE id = %s",
                (new_granary, legion_id)
            )
            await cur.execute(
                "UPDATE troops SET food = %s, update_time = %s WHERE id = %s",
                (db_new_food, get_uptime_ms(), target_troop_id)
            )

        await txn_conn.commit()

    # 事务成功后更新内存缓存
    legion["granary_current"] = new_granary
    troop["food"] = db_new_food

    logger.info(f"军团粮仓补给: operator={operator_user_id}, troop={target_troop_id}, food={food_amount}, granary={new_granary}, troop_food={db_new_food}")
    return True, {
        "troop_id": target_troop_id,
        "food_added": food_amount,
        "food_total": db_new_food,
        "legion_granary_remaining": new_granary,
    }


# ==================== 战斗结算时增加军团数据 ====================


async def add_legion_combat_reward(user_id, score):
    """战斗结算后，为军团增加积分和粮食"""
    member = legion_member_cache.get(user_id)
    if member is None:
        return

    legion_id = member["legion_id"]
    legion = legion_cache.get(legion_id)
    if legion is None:
        return

    int_score = int(score)
    if int_score <= 0:
        return

    # 1. 军团总战斗积分 1:1
    new_total = legion["total_combat_score"] + int_score
    await update_legion_field(legion_id, "total_combat_score", new_total)
    legion["total_combat_score"] = new_total

    # 2. 军团可用战斗积分 = 原积分 × 1/3
    available_delta = int(int_score / 3)
    if available_delta > 0:
        new_available = legion["available_combat_score"] + available_delta
        await update_legion_field(legion_id, "available_combat_score", new_available)
        legion["available_combat_score"] = new_available

    # 3. 缴获粮食 = 战斗积分 × 25，一半→军团粮仓，一半→个人粮仓
    food_gained = int_score * 25
    half_food = int(food_gained / 2)

    # 军团粮仓（上限检查）
    granary_space = legion["granary_max"] - legion["granary_current"]
    legion_food_add = min(half_food, granary_space)
    if legion_food_add > 0:
        new_granary = legion["granary_current"] + legion_food_add
        await update_legion_field(legion_id, "granary_current", new_granary)
        legion["granary_current"] = new_granary

    # 个人粮仓
    if half_food > 0:
        new_personal = member["personal_granary"] + half_food
        await update_member_field(user_id, "personal_granary", new_personal)
        member["personal_granary"] = new_personal

    # 4. 个人总积分和个人当前积分
    new_total_score = member["personal_total_score"] + int_score
    await update_member_field(user_id, "personal_total_score", new_total_score)
    member["personal_total_score"] = new_total_score

    new_current_score = member["personal_current_score"] + int_score
    await update_member_field(user_id, "personal_current_score", new_current_score)
    member["personal_current_score"] = new_current_score


# ==================== 军团阶段解锁（军团长/副军团长操作） ====================


def _get_stage_config(category):
    """获取指定类型的阶段配置列表"""
    if category == "granary":
        return GRANARY_STAGES, "granary_stage", get_granary_stage_cost
    elif category == "chest_ticket":
        return CHEST_TICKET_STAGES, "chest_ticket_stage", get_chest_ticket_stage_cost
    elif category == "buff":
        return BUFF_STAGES, "buff_stage", get_buff_stage_cost
    elif category == "special":
        return SPECIAL_STAGES, "special_stage", get_special_stage_cost
    return None, None, None


async def unlock_legion_stage(operator_user_id, category):
    """军团长/副军团长消耗军团可用来解锁兑换阶段"""
    # 权限校验：只有军团长和副军团长可以操作
    operator_member = legion_member_cache.get(operator_user_id)
    if operator_member is None:
        return False, "你不在军团中"
    if operator_member["role"] not in (ROLE_LEADER, ROLE_VICE):
        return False, "只有军团长和副军团长可以解锁阶段"

    legion_id = operator_member["legion_id"]
    legion = legion_cache.get(legion_id)
    if legion is None:
        return False, "军团不存在"

    stages, field_name, get_cost = _get_stage_config(category)
    if stages is None:
        return False, "未知的解锁类型"

    current_stage = legion.get(field_name, 0)
    # 宝箱货票类阶段范围 0-8，其他为 1-4
    max_stage = max(s["stage"] for s in stages)
    if current_stage >= max_stage:
        return False, "已达最高阶段，无法继续解锁"

    next_stage = current_stage + 1
    cost = get_cost(next_stage)
    if cost is None:
        return False, f"阶段{next_stage}配置不存在"

    if legion["available_combat_score"] < cost:
        return False, f"军团可用积分不足，需要{cost}，当前{legion['available_combat_score']}"

    # 扣除军团积分并更新阶段
    new_available = legion["available_combat_score"] - cost
    await update_legion_field(legion_id, "available_combat_score", new_available)
    legion["available_combat_score"] = new_available

    await update_legion_field(legion_id, field_name, next_stage)
    legion[field_name] = next_stage

    # 如果是粮仓扩展，还需要更新粮仓上限
    if category == "granary":
        new_max = get_granary_stage_max(next_stage)
        if new_max is not None:
            await update_legion_field(legion_id, "granary_max", new_max)
            legion["granary_max"] = new_max

    category_names = {
        "granary": "粮仓上限",
        "chest_ticket": "宝箱与货票",
        "buff": "加成类道具",
        "special": "特殊道具",
    }
    logger.info(f"军团阶段解锁: 军团={legion['name']}({legion_id}), "
                f"类型={category_names.get(category, category)}, 阶段={next_stage}, 消耗积分={cost}")

    return True, {
        "category": category,
        "stage": next_stage,
        "cost": cost,
        "available_combat_score": new_available,
    }


# ==================== 军团积分兑换道具（玩家个人操作） ====================


async def exchange_legion_item(user_id, item_name, quantity=1):
    """玩家使用个人当前积分兑换军团已解锁的道具"""
    if quantity <= 0:
        return False, "兑换数量必须为正数"

    member = legion_member_cache.get(user_id)
    if member is None:
        return False, "你不在军团中"

    legion_id = member["legion_id"]
    legion = legion_cache.get(legion_id)
    if legion is None:
        return False, "军团不存在"

    # 检查道具是否已解锁
    unlock_info = get_item_unlock_stage(item_name)
    if unlock_info is None:
        return False, f"道具【{item_name}】不在兑换列表中"
    unlock_category, required_stage = unlock_info

    if unlock_category == "chest_ticket":
        current_stage = legion.get("chest_ticket_stage", 0)
    elif unlock_category == "buff":
        current_stage = legion.get("buff_stage", 0)
    elif unlock_category == "special":
        current_stage = legion.get("special_stage", 0)
    else:
        return False, "未知道具类型"

    if current_stage < required_stage:
        return False, f"道具【{item_name}】尚未解锁，需要军团解锁阶段{required_stage}，当前{current_stage}"

    # 获取价格
    price = get_item_price(item_name)
    if price is None:
        return False, f"道具【{item_name}】价格未配置"

    total_price = price * quantity
    if member["personal_current_score"] < total_price:
        return False, f"个人积分不足，需要{total_price}，当前{member['personal_current_score']}"

    # 扣除个人积分
    new_score = member["personal_current_score"] - total_price
    await update_member_field(user_id, "personal_current_score", new_score)
    member["personal_current_score"] = new_score

    # 发放道具
    result = await add_item_to_user(user_id, item_name, quantity)
    if "error" in result:
        # 道具发放失败，回滚积分
        await update_member_field(user_id, "personal_current_score", member["personal_current_score"] + total_price)
        member["personal_current_score"] = member["personal_current_score"] + total_price
        return False, result["error"]

    logger.info(f"军团兑换: user={user_id}, item={item_name}×{quantity}, "
                f"消耗积分={total_price}, 剩余={new_score}")

    return True, {
        "item_name": item_name,
        "quantity": quantity,
        "price": price,
        "total_price": total_price,
        "personal_current_score": new_score,
        "item_result": result,
    }


# ==================== 查询可兑换列表 ====================


def get_legion_exchange_items(user_id):
    """获取当前军团已解锁的可兑换物品列表及价格"""
    member = legion_member_cache.get(user_id)
    if member is None:
        return None, "你不在军团中"

    legion = legion_cache.get(member["legion_id"])
    if legion is None:
        return None, "军团不存在"

    items = get_all_unlockable_items(
        legion.get("chest_ticket_stage", 0),
        legion.get("buff_stage", 0),
        legion.get("special_stage", 0),
    )

    return True, {
        "legion_id": member["legion_id"],
        "personal_current_score": member["personal_current_score"],
        "chest_ticket_stage": legion.get("chest_ticket_stage", 0),
        "buff_stage": legion.get("buff_stage", 0),
        "special_stage": legion.get("special_stage", 0),
        "exchange_items": items,
    }


# ==================== 军团阶段状态查询 ====================


def get_legion_stage_list(user_id):
    """获取军团四种类型当前阶段状态（对标 mission_list / tech_list）"""
    member = legion_member_cache.get(user_id)
    if member is None:
        return None, "你不在军团中"

    legion = legion_cache.get(member["legion_id"])
    if legion is None:
        return None, "军团不存在"

    available_score = legion.get("available_combat_score", 0)

    def _build_stage_info(stages, current, name, field_name):
        max_stage = max(s["stage"] for s in stages)
        if current >= max_stage:
            next_cost = 0
            is_maxed = True
        else:
            next_stage = current + 1
            next_cost = None
            for s in stages:
                if s["stage"] == next_stage:
                    next_cost = s["cost"]
                    break
            is_maxed = False
        return {
            "category": field_name,
            "category_name": name,
            "current_stage": current,
            "max_stage": max_stage,
            "next_cost": next_cost,
            "is_maxed": is_maxed,
            "can_afford": available_score >= next_cost if next_cost > 0 else False,
        }

    granary_current = legion.get("granary_stage", 0)
    chest_ticket_current = legion.get("chest_ticket_stage", 0)
    buff_current = legion.get("buff_stage", 0)
    special_current = legion.get("special_stage", 0)

    result = {
        "available_combat_score": available_score,
        "granary": _build_stage_info(GRANARY_STAGES, granary_current, "粮仓上限", "granary"),
        "chest_ticket": _build_stage_info(CHEST_TICKET_STAGES, chest_ticket_current, "宝箱与货票", "chest_ticket"),
        "buff": _build_stage_info(BUFF_STAGES, buff_current, "加成类道具", "buff"),
        "special": _build_stage_info(SPECIAL_STAGES, special_current, "特殊道具", "special"),
    }
    return True, result


def get_legion_stage_detail(user_id, category):
    """获取单个类型所有阶段的解锁条件和可解锁道具（对标 mission_detail / tech_detail）"""
    member = legion_member_cache.get(user_id)
    if member is None:
        return None, "你不在军团中"

    legion = legion_cache.get(member["legion_id"])
    if legion is None:
        return None, "军团不存在"

    if category == "granary":
        stages = GRANARY_STAGES
        current = legion.get("granary_stage", 0)
        category_name = "粮仓上限"
        stages_out = []
        for s in stages:
            stage_num = s["stage"]
            stages_out.append({
                "stage": stage_num,
                "cost": s["cost"],
                "unlocked": stage_num <= current,
                "effect": f"粮仓上限提升至{s['max']}",
            })
    elif category == "chest_ticket":
        stages = CHEST_TICKET_STAGES
        current = legion.get("chest_ticket_stage", 0)
        category_name = "宝箱与货票"
        stages_out = []
        for s in stages:
            stage_num = s["stage"]
            items = []
            for item_name in s.get("chests", []) + s.get("tickets", []):
                price = s.get("prices", {}).get(item_name, 0)
                items.append({"name": item_name, "price": price})
            stages_out.append({
                "stage": stage_num,
                "cost": s["cost"],
                "unlocked": stage_num <= current,
                "items": items,
            })
    elif category == "buff":
        stages = BUFF_STAGES
        current = legion.get("buff_stage", 0)
        category_name = "加成类道具"
        stages_out = []
        for s in stages:
            stage_num = s["stage"]
            items = []
            for item_name in s.get("items", []):
                price = s.get("prices", {}).get(item_name, 0)
                items.append({"name": item_name, "price": price})
            if stage_num == 4:
                for name in SKILL_BOOK_LIST:
                    items.append({"name": name, "price": SKILL_BOOK_PRICE})
            stages_out.append({
                "stage": stage_num,
                "cost": s["cost"],
                "unlocked": stage_num <= current,
                "items": items,
            })
    elif category == "special":
        stages = SPECIAL_STAGES
        current = legion.get("special_stage", 0)
        category_name = "特殊道具"
        stages_out = []
        for s in stages:
            stage_num = s["stage"]
            items = []
            for item_name in s.get("items", []):
                price = s.get("prices", {}).get(item_name, 0)
                items.append({"name": item_name, "price": price})
            stages_out.append({
                "stage": stage_num,
                "cost": s["cost"],
                "unlocked": stage_num <= current,
                "items": items,
            })
    else:
        return None, "无效的类型，可选: granary, chest_ticket, buff, special"

    return True, {
        "category": category,
        "category_name": category_name,
        "current_stage": current,
        "stages": stages_out,
    }


# ==================== 灵珠使用（土灵珠/水灵珠） ====================


async def use_pearl_on_fief(user_id, item_name, town_id):
    """在封地城池上使用土灵珠/水灵珠，提高该城池资源收益
    注意：灵珠之间是覆盖关系，不是升级关系。
    使用水灵珠会覆盖已有的土灵珠效果（旧效果销毁），反之则被 cannot_downgrade 拦截。
    """
    if item_name not in PEARL_CONFIG:
        return False, "该道具不是灵珠"

    pearl_cfg = PEARL_CONFIG[item_name]

    # 校验城池存在且等级≤3
    town = towns_cache.get(town_id)
    if town is None:
        return False, "城池不存在"
    if town.get("level", 1) > PEARL_MAX_TOWN_LEVEL:
        return False, f"灵珠只能对等级≤{PEARL_MAX_TOWN_LEVEL}的城池使用，当前城池等级{town.get('level')}"

    # 校验玩家在该城池有封地
    has_fief = False
    for fid, fief in fief_cache.items():
        if fief["user_id"] == user_id and fief["town_id"] == town_id:
            has_fief = True
            break
    if not has_fief:
        return False, "你在该城池没有封地，无法使用灵珠"

    # 检查是否已有灵珠效果
    cache_key = (user_id, town_id)
    existing_bonus = fief_item_effects_cache.get(cache_key)

    if existing_bonus is not None:
        # 水灵珠 → 土灵珠：拒绝
        if pearl_cfg.get("cannot_downgrade") and existing_bonus > pearl_cfg["bonus"]:
            return False, f"该城池已使用水灵珠（+{existing_bonus}），效果更优，无法替换为土灵珠"
        # 土灵珠 → 水灵珠：覆盖
        if existing_bonus == pearl_cfg["bonus"]:
            return False, f"该城池已使用{item_name}，效果相同"

    # 写入数据库
    await upsert_fief_item_effect(user_id, town_id, item_name, pearl_cfg["bonus"])
    # 更新缓存
    fief_item_effects_cache[cache_key] = pearl_cfg["bonus"]

    logger.info(f"灵珠使用: user={user_id}, item={item_name}, town_id={town_id}, "
                f"bonus={pearl_cfg['bonus']}, 旧bonus={existing_bonus}")

    return True, {
        "town_id": town_id,
        "item_name": item_name,
        "bonus": pearl_cfg["bonus"],
        "description": pearl_cfg["description"],
    }