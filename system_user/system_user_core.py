from data.global_data import user_cache, phone_index
from system_user.system_user_db import get_all_users, get_user_by_username, get_user_by_phone, insert_user


async def load_all_users_to_cache():
    users = await get_all_users()
    user_cache.clear()
    phone_index.clear()
    for user in users:
        user_cache[user["username"]] = user
        if user.get("phone"):
            phone_index[user["phone"]] = user["username"]


def is_username_exists(username):
    return username in user_cache


def is_phone_exists(phone):
    return phone in phone_index


def verify_credentials(username, password):
    user = user_cache.get(username)
    if user is None:
        return False, None
    if user["password"] != password:
        return False, None
    return True, user


async def register_user(username, password, phone):
    if is_username_exists(username):
        return False, "用户名已存在"
    if phone and is_phone_exists(phone):
        return False, "手机号已存在"

    db_user = await get_user_by_username(username)
    if db_user:
        return False, "用户名已存在"
    if phone:
        db_phone = await get_user_by_phone(phone)
        if db_phone:
            return False, "手机号已存在"

    user_id = await insert_user(username, password, phone)

    user = {
        "id": user_id,
        "username": username,
        "password": password,
        "phone": phone,
        "zt": "0"
    }
    user_cache[username] = user
    if phone:
        phone_index[phone] = username
    return True, user