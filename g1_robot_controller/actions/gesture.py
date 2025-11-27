"""
gesture.py - 手势动作模块

功能说明:
    这个模块定义了机器人可以执行的各种面部和身体手势动作。
    包括挥手、点头、摇头、竖起大拇指、鞠躬、耸肩等。

支持的手势列表:
    - wave: 挥手（友好问候）
    - nod: 点头（同意、确认）
    - shake_head: 摇头（否定、拒绝）
    - thumbs_up: 竖起大拇指（点赞、同意）
    - bow: 鞠躬（尊重、感谢）
    - shrug: 耸肩（不知道、无所谓）

核心函数:
    - execute_gesture(gesture_name): 执行指定的手势
    - get_available_gestures(): 获取所有可用手势

使用例子:
    execute_gesture("wave")        # 挥手
    execute_gesture("nod")         # 点头
    gestures = get_available_gestures()
    print(list(gestures.keys()))   # ['wave', 'nod', ...]
"""

import logging
from typing import Optional
from .robot_api import get_robot_api

logger = logging.getLogger(__name__)

# 可用的手势字典
# 键: 手势名称（英文，小写）
# 值: 手势的中英文描述
GESTURES = {
    "wave": "Waving hand",           # 挥手
    "nod": "Nodding head",           # 点头
    "shake_head": "Shaking head",    # 摇头
    "thumbs_up": "Thumbs up",        # 竖起大拇指
    "bow": "Bowing",                 # 鞠躬
    "shrug": "Shrugging",            # 耸肩
}


def execute_gesture(gesture_name: str, **kwargs) -> bool:
    """
    执行指定的手势动作
    
    工作流程:
        1. 将手势名称转换为小写并去除空格
        2. 检查手势是否在GESTURES字典中
        3. 如果不存在，记录警告并返回False
        4. 记录执行日志
        5. 调用实际的电机控制API（TODO部分）
        6. 捕获异常并记录错误
    
    参数:
        gesture_name: 要执行的手势名称（不区分大小写）
                     示例: "wave", "nod", "shake_head" 等
    
    返回:
        True - 手势执行成功（或至少开始执行）
        False - 手势不存在或执行失败
    
    日志输出:
        未知手势: ⚠️ Unknown gesture: xxx. Available: [...]
        执行中: 🤖 Executing gesture: wave - Waving hand
        执行失败: ❌ Failed to execute gesture xxx: error message
    
    例子:
        execute_gesture("wave")        # 挥手
        execute_gesture("NODS")        # 自动转换为lowercase → nod(失败，拼写错误)
        execute_gesture("nod")         # 点头
    
    注意:
        当前实现中 TODO 部分需要与机器人电机控制API集成
        该部分会调用实际的运动控制库（例如 unitree_sdk2py）
    """
    gesture_name = gesture_name.lower().strip()
    
    if gesture_name not in GESTURES:
        logger.warning(f"Unknown gesture: {gesture_name}. Available: {list(GESTURES.keys())}")
        return False
    
    try:
        logger.info(f"🤖 Executing gesture: {gesture_name} - {GESTURES[gesture_name]}")
        robot = get_robot_api()
        return robot.execute_gesture(gesture_name, **kwargs)
    except Exception as e:
        logger.error(f"Failed to execute gesture {gesture_name}: {e}")
        return False


def get_available_gestures() -> dict:
    """
    获取所有可用的手势
    
    功能:
        - 返回GESTURES字典的副本
        - 防止外部代码直接修改GESTURES
    
    返回:
        手势字典的副本，格式为：
        {
            "gesture_name": "描述",
            "wave": "Waving hand",
            "nod": "Nodding head",
            ...
        }
    
    例子:
        gestures = get_available_gestures()
        print(list(gestures.keys()))  # ['wave', 'nod', 'shake_head', ...]
        print(gestures['wave'])       # 'Waving hand'
    
    说明:
        返回的是副本（.copy()），所以修改返回值不会影响原始GESTURES
    """
    return GESTURES.copy()
