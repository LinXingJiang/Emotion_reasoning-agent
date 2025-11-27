"""
system.py - 系统命令模块

功能说明:
    这个模块定义了机器人可以执行的各种系统级命令。
    这些命令控制机器人的整体状态和行为，例如站起、坐下、紧急停止等。

支持的系统命令:
    - stand_up: 从坐姿站起来
    - sit_down: 坐下
    - stop: 停止所有动作
    - reset: 复位到初始状态
    - emergency_stop: 紧急停止（E-stop）
    - power_off: 关闭电源
    - power_on: 启动电源

核心函数:
    - execute_system_command(command_name): 执行指定的系统命令
    - get_available_commands(): 获取所有可用命令

使用例子:
    execute_system_command("stand_up")       # 站起
    execute_system_command("sit_down")       # 坐下
    execute_system_command("reset")          # 复位
    execute_system_command("emergency_stop") # 紧急停止
    commands = get_available_commands()
    print(list(commands.keys()))             # ['stand_up', 'sit_down', ...]

说明:
    紧急停止命令会记录一条CRITICAL级别的日志，表示系统进入紧急状态。
"""

import logging
from typing import Optional
from .robot_api import get_robot_api

logger = logging.getLogger(__name__)

# 可用的系统命令字典
# 键: 命令名称（英文，小写）
# 值: 命令的描述
SYSTEM_COMMANDS = {
    "stand_up": "Stand up from sitting position",         # 从坐姿站起
    "sit_down": "Sit down",                               # 坐下
    "stop": "Stop all actions",                           # 停止所有动作
    "reset": "Reset robot to home position",              # 复位到初始位置
    "emergency_stop": "Emergency stop (E-stop)",          # 紧急停止
    "power_off": "Power off the robot",                   # 关闭电源
    "power_on": "Power on the robot",                     # 启动电源
}


def execute_system_command(command_name: str, **kwargs) -> bool:
    """
    执行指定的系统命令
    
    工作流程:
        1. 将命令名称转换为小写并去除空格
        2. 检查命令是否在SYSTEM_COMMANDS字典中
        3. 如果不存在，记录警告并返回False
        4. 对于emergency_stop命令，记录CRITICAL级别的日志
        5. 记录命令执行日志
        6. 调用实际的系统控制API（TODO部分）
        7. 捕获异常并记录错误
    
    参数:
        command_name: 要执行的系统命令名称（不区分大小写）
                     示例: "stand_up", "sit_down", "reset" 等
    
    返回:
        True - 系统命令执行成功（或至少开始执行）
        False - 命令不存在或执行失败
    
    日志输出:
        未知命令: ⚠️ Unknown command: xxx. Available: [...]
        执行中: ⚙️ Executing system command: stand_up - Stand up from sitting position
        紧急停止: 🚨 EMERGENCY STOP ACTIVATED!（CRITICAL级别）
        执行失败: ❌ Failed to execute system command xxx: error message
    
    例子:
        execute_system_command("stand_up")       # 站起
        execute_system_command("sit_down")       # 坐下
        execute_system_command("RESET")          # 自动转换为lowercase → reset
        execute_system_command("emergency_stop") # 紧急停止（记录CRITICAL日志）
    
    特殊处理:
        emergency_stop命令会记录一条CRITICAL级别的日志，
        以警告系统管理员已进入紧急停止状态。
    
    注意:
        当前实现中 TODO 部分需要与机器人系统控制API集成
        该部分会调用实际的系统控制库（例如 unitree_sdk2py 的 system API）
    """
    command_name = command_name.lower().strip()
    
    if command_name not in SYSTEM_COMMANDS:
        logger.warning(f"Unknown command: {command_name}. Available: {list(SYSTEM_COMMANDS.keys())}")
        return False
    
    try:
        logger.info(f"⚙️ Executing system command: {command_name} - {SYSTEM_COMMANDS[command_name]}")
        robot = get_robot_api()
        # Special handling for emergency stop
        if command_name == "emergency_stop":
            logger.critical("🚨 EMERGENCY STOP ACTIVATED!")
            # Immediately stop robot and cancel ongoing actions
            robot.stop()
            # Also cancel any running actions through ActionExecutor
            try:
                # Import locally to avoid circular import
                from .action_executor import get_executor
                executor = get_executor()
                executor.cancel_all()
            except Exception as ex:
                logger.warning(f"Failed to cancel actions via executor: {ex}")
            return True

        # Map commands to robot API where available
        if command_name == "stand_up":
            # Might be a complex sequence; placeholder
            return True
        if command_name == "sit_down":
            return True
        if command_name == "reset":
            return True
        return True
    except Exception as e:
        logger.error(f"Failed to execute system command {command_name}: {e}")
        return False


def get_available_commands() -> dict:
    """
    获取所有可用的系统命令
    
    功能:
        - 返回SYSTEM_COMMANDS字典的副本
        - 防止外部代码直接修改SYSTEM_COMMANDS
    
    返回:
        系统命令字典的副本，格式为：
        {
            "stand_up": "Stand up from sitting position",
            "sit_down": "Sit down",
            ...
        }
    
    例子:
        commands = get_available_commands()
        print(list(commands.keys()))  # ['stand_up', 'sit_down', 'stop', ...]
        print(commands['stand_up'])   # 'Stand up from sitting position'
    
    说明:
        返回的是副本（.copy()），所以修改返回值不会影响原始SYSTEM_COMMANDS
    """
    return SYSTEM_COMMANDS.copy()
