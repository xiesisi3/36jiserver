# 行军常量定义

# 黄金加速档位
# 加速30%：消耗8黄金/每支部队，行军时间×0.7
# 加速50%：消耗16黄金/每支部队，行军时间×0.5
GOLD_PER_ACCEL_30 = 8
GOLD_PER_ACCEL_50 = 16
ACCEL_FACTOR_30 = 0.7
ACCEL_FACTOR_50 = 0.5
ACCEL_FACTOR_NONE = 1.0

# 行军最大延迟时间（秒）
MAX_MARCH_DELAY = 24 * 3600

# 行军粮食消耗公式参数
# 单兵消耗 = ceil(总路径距离 × 攻击消耗粮食 / 250)
# 其中 250 = 50(距离系数) × 5(粮食消耗比例)
FOOD_DISTANCE_DENOMINATOR = 50
FOOD_CONSUMPTION_RATIO = 5
FOOD_DISTANCE_FACTOR = FOOD_DISTANCE_DENOMINATOR * FOOD_CONSUMPTION_RATIO

# 行军时间计算公式参数
# minutes = distance * 14 / min_speed / source_traffic_mult / target_traffic_mult
TRAVEL_TIME_BASE = 14

# 交通值系数表（从 town_data_config.py 的 TOWN_ATTR_EFFECTS 提取）
TRAFFIC_COEFFICIENT_TABLE = [
    {"min": 0, "max": 9999, "speed_multiplier": 0.65},
    {"min": 10000, "max": 19999, "speed_multiplier": 0.80},
    {"min": 20000, "max": 29999, "speed_multiplier": 0.95},
    {"min": 30000, "max": 39999, "speed_multiplier": 1.10},
    {"min": 40000, "max": 49999, "speed_multiplier": 1.25},
    {"min": 50000, "max": 59999, "speed_multiplier": 1.40},
    {"min": 60000, "max": 69999, "speed_multiplier": 1.55},
    {"min": 70000, "max": 79999, "speed_multiplier": 1.70},
    {"min": 80000, "max": 89999, "speed_multiplier": 1.85},
    {"min": 90000, "max": 100000, "speed_multiplier": 2.00},
]