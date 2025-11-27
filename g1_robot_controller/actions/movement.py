"""
movement.py - 运动动作模块

功能说明:
    这个模块定义了机器人可以执行的各种运动和移动动作。
    包括前进、后退、左右移动、转身、行走等。

支持的运动列表:
    - forward: 向前走
    - backward: 向后走
    - left: 左移
    - right: 右移
    - turn_left: 左转
    - turn_right: 右转
    - walk: 开始行走
    - stop: 停止运动

核心函数:
    - execute_movement(movement_name, distance): 执行指定的运动
    - get_available_movements(): 获取所有可用运动

使用例子:
    execute_movement("forward")           # 向前走
    execute_movement("forward", 1.5)      # 向前走1.5米
    execute_movement("turn_left")         # 左转
    movements = get_available_movements()
    print(list(movements.keys()))         # ['forward', 'backward', ...]
"""

import logging
from typing import Optional
from .robot_api import get_robot_api

logger = logging.getLogger(__name__)

# 可用的运动字典
# 键: 运动名称（英文，小写）
# 值: 运动的描述
MOVEMENTS = {
    "forward": "Move forward",       # 向前
    "backward": "Move backward",     # 向后
    "left": "Move left",             # 向左
    "right": "Move right",           # 向右
    "turn_left": "Turn left",        # 左转
    "turn_right": "Turn right",      # 右转
    "walk": "Start walking",         # 行走
    "stop": "Stop moving",           # 停止
}


def execute_movement(movement_name: str, distance: Optional[float] = None) -> bool:
    """
    执行指定的运动动作
    
    工作流程:
        1. 将运动名称转换为小写并去除空格
        2. 检查运动是否在MOVEMENTS字典中
        3. 如果不存在，记录警告并返回False
        4. 如果提供了距离参数，在日志中显示
        5. 记录执行日志
        6. 调用实际的电机控制API（TODO部分）
        7. 捕获异常并记录错误
    
    参数:
        movement_name: 要执行的运动名称（不区分大小写）
                      示例: "forward", "backward", "turn_left" 等
        distance: 可选的运动距离（米）
                 示例: 1.5 表示前进1.5米
                 如果不提供，则执行该运动的默认行为
    
    返回:
        True - 运动执行成功（或至少开始执行）
        False - 运动不存在或执行失败
    
    日志输出:
        未知运动: ⚠️ Unknown movement: xxx. Available: [...]
        执行中(有距离): 🚶 Executing movement: forward - Move forward (1.5m)
        执行中(无距离): 🚶 Executing movement: turn_left - Turn left
        执行失败: ❌ Failed to execute movement xxx: error message
    
    例子:
        execute_movement("forward")           # 向前走（使用默认行为）
        execute_movement("forward", 2.0)      # 向前走2米
        execute_movement("turn_left")         # 左转
        execute_movement("STOP")              # 自动转换为lowercase → stop
    
    注意:
        当前实现中 TODO 部分需要与机器人运动控制API集成
        该部分会调用实际的运动控制库（例如 unitree_sdk2py 的 motion API）
    """
    movement_name = movement_name.lower().strip()
    
    if movement_name not in MOVEMENTS:
        logger.warning(f"Unknown movement: {movement_name}. Available: {list(MOVEMENTS.keys())}")
        return False
    
    try:
        robot = get_robot_api()
        if distance:
            logger.info(f"🚶 Executing movement: {movement_name} - {MOVEMENTS[movement_name]} ({distance}m)")
        else:
            logger.info(f"🚶 Executing movement: {movement_name} - {MOVEMENTS[movement_name]}")

        # High-level API mapping
        if movement_name == "forward":
            return robot.move_forward(distance if distance else 0.5, speed=0.2)
        elif movement_name == "backward":
            # Move backward by moving forward with negative distance is an option
            return robot.move_forward(distance if distance else 0.5, speed=0.2)
        elif movement_name == "turn_left":
            return robot.turn(-90.0 if distance is None else -distance)
        elif movement_name == "turn_right":
            return robot.turn(90.0 if distance is None else distance)
        elif movement_name == "stop":
            return robot.stop()
        elif movement_name == "walk":
            return robot.move_forward(distance if distance else 0.5)
        else:
            logger.warning(f"Movement {movement_name} not implemented in robot_api mapping")
            return False
    except Exception as e:
        logger.error(f"Failed to execute movement {movement_name}: {e}")
        return False


def get_available_movements() -> dict:
    """
    获取所有可用的运动
    
    功能:
        - 返回MOVEMENTS字典的副本
        - 防止外部代码直接修改MOVEMENTS
    
    返回:
        运动字典的副本，格式为：
        {
            "forward": "Move forward",
            "backward": "Move backward",
            ...
        }
    
    例子:
        movements = get_available_movements()
        print(list(movements.keys()))  # ['forward', 'backward', 'left', ...]
        print(movements['forward'])    # 'Move forward'
    
    说明:
        返回的是副本（.copy()），所以修改返回值不会影响原始MOVEMENTS
    """
    return MOVEMENTS.copy()
