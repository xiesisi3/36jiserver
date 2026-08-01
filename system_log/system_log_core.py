from system_log.system_log_db import insert_log
from system_log.system_log_dic import get_log_id


async def record_login_log(user_id, success):
    log_id = get_log_id("登录")
    if not log_id:
        return
    await insert_log(log_id, user_id, user_id, "0" if success else "1")


async def record_register_log(user_id, success):
    log_id = get_log_id("注册")
    if not log_id:
        return
    await insert_log(log_id, user_id, user_id, "0" if success else "1")