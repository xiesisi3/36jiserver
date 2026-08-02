import json
import logging
import aiomysql
from data.global_data import (
    legion_cache, legion_member_cache, legion_member_index,
    user_resource_cache, user_nation_cache, troop_cache,
)
from legion.legion_db import (
    create_tables, get_all_legions, get_legion_by_id, get_legion_by_name,
    insert_legion, update_legion_field,
    get_all_legion_members, get_member_by_user, get_members_by_legion,
    insert_legion_member, update_member_role, update_member_field, delete_member,
    get_application, upsert_application, update_application_status, get_pending_applications,
)
from notification.notification_core import publish_system_message
from user_resource.user_resource_db import update_user_resource_field
from core.connection import send_to_user
from core.database import get_pool
from troop.troop_utils import calculate_max_carry_food
from server_timer.server_timer_core import get_uptime_ms

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

    logger.info(f"军团模块初始化完成: {len(legion_cache)} 个军团, {len(legion_member_cache)} 个成员")


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

    return {
        "id": legion["id"],
        "nation_id": legion["nation_id"],
        "name": legion["name"],
        "description": legion["description"],
        "total_combat_score": legion["total_combat_score"],
        "available_combat_score": legion["available_combat_score"],
        "granary_max": legion["granary_max"],
        "granary_current": legion["granary_current"],
        "member_count": len(members),
        "create_time": str(legion["create_time"]) if legion.get("create_time") else "",
        "members": members,
    }


# ==================== 军团列表 ====================


def get_legions_by_nation(nation_id):
    result = []
    for lid, legion in legion_cache.items():
        if legion["nation_id"] == nation_id:
            result.append({
                "id": legion["id"],
                "name": legion["name"],
                "description": legion["description"],
                "member_count": _get_legion_member_count(lid),
                "total_combat_score": legion["total_combat_score"],
                "create_time": str(legion["create_time"]) if legion.get("create_time") else "",
            })
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
        content=f"玩家 {player_name} 申请加入你的军团【{legion['name']}】",
        category="军团",
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
            title="军团申请通过",
            content=f"你已加入军团【{legion_name}】",
            category="军团",
        )

        # 玩家在线则实时推送加入军团通知
        await send_to_user(application_user_id, {
            "type": "legion_join",
            "code": 0,
            "data": {
                "legion_id": legion_id,
                "legion_name": legion_name,
                "msg": f"恭喜 {player_name} 玩家成功加入军团【{legion_name}】",
            },
        })

        logger.info(f"军团申请通过: {player_name}({application_user_id}) 加入 {legion_name}({legion_id})")
        return True, "已同意申请"
    else:
        await update_application_status(legion_id, application_user_id, 2)

        player_name = (user_resource_cache.get(application_user_id, {}) or {}).get("player_name", "")
        legion_name = legion_cache[legion_id]["name"]

        await publish_system_message(
            receiver_id=application_user_id,
            receiver_name=player_name,
            title="军团申请被拒绝",
            content=f"你申请加入军团【{legion_name}】的请求已被拒绝",
            category="军团",
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