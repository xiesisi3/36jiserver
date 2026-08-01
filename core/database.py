import aiomysql
from config.DB_CONFIG import DB_CONFIG

_pool = None


async def init_pool():
    global _pool
    _pool = await aiomysql.create_pool(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        db=DB_CONFIG["database"],
        charset=DB_CONFIG["charset"],
        autocommit=True,
    )


async def close_pool():
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()
        _pool = None


def get_pool():
    return _pool