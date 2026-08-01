BUILDING_CONFIG = {
    "城主府": {
        "max_count": 1,
        "can_demolish": False,
        "desc": "封地核心,不升级这个就没法升级别的",
        "max_level": 20,
    },
    "军乐台": {
        "max_count": 1,
        "can_demolish": True,
        "desc": "可加快兵种建造速度,一个封地只能有一个",
        "max_level": 20,
    },
    "林场": {
        "max_count": -1,
        "can_demolish": True,
        "desc": "可收获木材资源，最高20级",
        "max_level": 20,
    },
    "农场": {
        "max_count": -1,
        "can_demolish": True,
        "desc": "可收获粮食资源，最高20级",
        "max_level": 20,
    },
    "矿场": {
        "max_count": -1,
        "can_demolish": True,
        "desc": "可收获铁矿资源，最高20级",
        "max_level": 20,
    },
    "民户": {
        "max_count": -1,
        "can_demolish": True,
        "desc": "可收获铜钱资源，最高20级",
        "max_level": 20,
    },
    "步兵营": {
        "max_count": 5,
        "can_demolish": True,
        "desc": "可训练步兵，等级越高训练速度越快，最高20级",
        "max_level": 20,
    },
    "弓兵营": {
        "max_count": 5,
        "can_demolish": True,
        "desc": "可训练弓兵，等级越高训练速度越快，最高20级",
        "max_level": 20,
    },
    "骑兵营": {
        "max_count": 5,
        "can_demolish": True,
        "desc": "可训练骑兵，等级越高训练速度越快，最高20级",
        "max_level": 20,
    },
    "空地": {
        "max_count": -1,
        "can_demolish": False,
        "desc": "可建造建筑",
        "max_level": 20,
    },
}

BUILDABLE_BUILDINGS = ["城主府", "林场", "农场", "矿场", "民户", "步兵营", "弓兵营", "骑兵营", "军乐台"]

RESOURCE_BUILDINGS = ["林场", "农场", "矿场", "民户"]

BARRACK_BUILDINGS = ["步兵营", "弓兵营", "骑兵营"]

BARRACK_TROOP_MAP = {
    "步兵营": "步兵系",
    "弓兵营": "弓兵系",
    "骑兵营": "骑兵系",
}

GRID_COLS = 6
GRID_ROWS = 6

INVALID_CELLS = {(0, 0), (0, 5), (5, 0), (5, 5)}

DEFAULT_FIEF_BUILDINGS = [
    (1, 1, "城主府", 20),
    (1, 2, "农场", 20),
    (1, 3, "林场", 20),
    (1, 4, "矿场", 20),
    (2, 1, "民户", 20),
]

MAX_FIEF_PER_USER = 24