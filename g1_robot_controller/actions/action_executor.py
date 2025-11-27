"""
action_executor.py - 动作执行器模块

功能说明:
    这个模块提供了一个中央动作执行器，用于管理和路由所有机器人动作。
    支持三种内置动作类型（手势、运动、系统）以及自定义动作处理器。

主要特性:
    1. 动作路由 - 根据action_type将请求路由到适当的处理器
    2. 执行历史 - 记录所有已执行的动作
    3. 自定义处理器 - 支持注册自定义动作处理器
    4. 动作序列 - 支持执行多个动作的序列
    5. 动作查询 - 查看所有可用的动作

内置动作类型:
    - gesture: 手势动作（wave, nod等）
    - movement: 运动动作（forward, backward等）
    - system: 系统命令（stand_up, sit_down等）

数据流:
    action请求 → ActionExecutor.execute()
         ↓
    检查自定义处理器/内置处理器
         ↓
    调用相应的处理器函数
         ↓
    记录执行历史
         ↓
    返回成功/失败状态

使用例子:
    executor = get_executor()
    
    # 执行单个动作
    executor.execute("gesture", "wave")
    executor.execute("movement", "forward", distance=1.5)
    executor.execute("system", "stand_up")
    
    # 执行动作序列
    actions = [
        {"type": "gesture", "name": "wave"},
        {"type": "movement", "name": "forward", "distance": 1.0},
        {"type": "gesture", "name": "nod"}
    ]
    executor.execute_sequence(actions)
    
    # 查看可用动作
    available = executor.get_available_actions()
    print(available["gesture"])  # ['wave', 'nod', ...]
"""

import logging
import threading
import uuid
from typing import Dict, Any, Optional, Callable

from . import gesture, movement, system

logger = logging.getLogger(__name__)

# 动作类型到处理器的映射
# 定义了内置的三种动作类型及其对应的处理函数
ACTION_HANDLERS = {
    "gesture": gesture.execute_gesture,           # 手势动作处理器
    "movement": movement.execute_movement,       # 运动动作处理器
    "system": system.execute_system_command,     # 系统命令处理器
}


class ActionExecutor:
    """
    动作执行器 - 中央动作管理和路由系统
    
    核心功能:
        1. 管理内置和自定义的动作处理器
        2. 路由动作请求到相应的处理器
        3. 记录所有已执行的动作
        4. 支持动作序列执行
        5. 提供可用动作查询
    
    数据结构:
        handlers: 内置处理器字典，包含gesture/movement/system
        custom_handlers: 用户自定义处理器字典
        execution_history: 执行历史列表，记录每个已执行的动作
    
    执行流程:
        1. 检查custom_handlers中是否有对应的处理器
        2. 如果没有，检查handlers中的内置处理器
        3. 如果找到处理器，调用它执行动作
        4. 记录执行结果到execution_history
        5. 返回执行成功/失败状态
    
    使用例子:
        executor = ActionExecutor()
        
        # 执行单个动作
        executor.execute("gesture", "wave")
        
        # 执行序列
        executor.execute_sequence([
            {"type": "gesture", "name": "wave"},
            {"type": "movement", "name": "forward"}
        ])
        
        # 查看可用动作
        actions = executor.get_available_actions()
    """
    
    def __init__(self):
        """
        初始化动作执行器
        
        初始化的属性:
            handlers: 内置处理器的副本
                     包含 gesture, movement, system 三种类型
            custom_handlers: 自定义处理器字典（初始为空）
            execution_history: 执行历史列表（初始为空）
                             每个元素是一个字典，记录：
                             {
                                 "action_type": str,
                                 "action_name": str,
                                 "success": bool
                             }
        
        说明:
            使用 .copy() 复制ACTION_HANDLERS，避免共享全局状态。
        """
        self.handlers: Dict[str, Callable] = ACTION_HANDLERS.copy()
        self.custom_handlers: Dict[str, Callable] = {}
        self.execution_history = []
        # running_actions: action_id -> {thread, cancel_event, action_type, action_name}
        self.running_actions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
    
    def register_handler(self, action_type: str, handler: Callable) -> None:
        """
        注册自定义动作处理器
        
        说明:
            - 允许用户扩展系统支持的动作类型
            - 自定义处理器优先于内置处理器被调用
            - 适合集成新的机器人功能
        
        参数:
            action_type: 自定义动作类型的标识符
                        示例: "dance", "recognition", "camera_capture" 等
            handler: 处理函数
                    签名: def handler(action_name: str, **kwargs) -> bool
                    返回True表示成功，False表示失败
        
        例子:
            def my_handler(action_name, **kwargs):
                print(f"执行自定义动作: {action_name}")
                return True
            
            executor.register_handler("dance", my_handler)
            executor.execute("dance", "waltz")
        """
        self.custom_handlers[action_type] = handler
        logger.info(f"Registered custom action handler: {action_type}")
    
    def execute(self, action_type: str, action_name: str, run_async: bool = False, **kwargs):
        """
        执行一个动作
        
        工作流程:
            1. 首先在custom_handlers中查找处理器
            2. 如果未找到，在handlers中查找内置处理器
            3. 如果都未找到，记录错误并返回False
            4. 调用处理器执行动作（传递action_name和其他kwargs）
            5. 记录执行结果到execution_history
            6. 返回执行状态
        
        参数:
            action_type: 动作类型（gesture, movement, system 或自定义类型）
            action_name: 具体动作名称
                        示例: "wave", "forward", "stand_up"
            **kwargs: 额外的参数，传递给处理器函数
                     示例: distance=1.5（用于movement动作）
        
        返回:
            True - 动作执行成功
            False - 动作执行失败或处理器不存在
        
        执行历史:
            每次执行都会向execution_history添加一条记录：
            {
                "action_type": "gesture",
                "action_name": "wave",
                "success": True
            }
        
        例子:
            executor.execute("gesture", "wave")
            executor.execute("movement", "forward", distance=1.5)
            
            # 检查执行历史
            print(executor.execution_history)
        
        错误处理:
            - 找不到处理器: 记录error日志，返回False
            - 处理器执行异常: 捕获异常，记录error日志，返回False
        """
        # Check custom handlers first
        handler = self.custom_handlers.get(action_type) or self.handlers.get(action_type)
        
        if handler is None:
            logger.error(f"No handler for action type: {action_type}")
            return False
        
        try:
            # If run_async, schedule in a thread and return an action_id
            if run_async:
                cancel_event = threading.Event()

                def _run():
                    success = False
                    try:
                        # pass cancel_event to handler via kwargs
                        _kwargs = kwargs.copy()
                        _kwargs["cancel_event"] = cancel_event
                        success = handler(action_name, **_kwargs)
                        return success
                    except Exception as e:
                        logger.error(f"Action handler exception: {e}")
                        return False
                    finally:
                        # Update history and cleanup
                        with self._lock:
                            self.execution_history.append({
                                "action_type": action_type,
                                "action_name": action_name,
                                "success": success,
                                "action_id": act_id,
                                "async": True,
                            })
                            if act_id in self.running_actions:
                                del self.running_actions[act_id]

                act_id = str(uuid.uuid4())
                thread = threading.Thread(target=_run, name=f"action-{act_id}")
                with self._lock:
                    self.running_actions[act_id] = {
                        "thread": thread,
                        "cancel_event": cancel_event,
                        "action_type": action_type,
                        "action_name": action_name,
                    }
                thread.daemon = True
                thread.start()
                return act_id

            # Synchronous execution
            success = handler(action_name, **kwargs)
            self.execution_history.append({
                "action_type": action_type,
                "action_name": action_name,
                "success": success,
                "async": False,
            })
            return success
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return False
    
    def execute_sequence(self, actions: list) -> int:
        """
        执行一个动作序列
        
        工作流程:
            1. 遍历actions列表中的每个动作
            2. 验证动作格式（必须是字典）
            3. 提取type和name字段
            4. 其他字段作为kwargs传递给execute()
            5. 统计成功执行的动作数量
            6. 记录总体执行日志
        
        参数:
            actions: 动作列表，每个元素是一个字典：
                    {
                        "type": "gesture",        # 必需
                        "name": "wave",           # 必需
                        "distance": 1.5           # 可选：会作为kwargs传递
                    }
        
        返回:
            成功执行的动作数量（整数）
            示例: 执行3个动作，成功2个，返回2
        
        日志输出:
            - 无效动作: ❌ Invalid action at index N: ...
            - 序列完成: ✅ Action sequence completed: X/Y successful
        
        例子:
            actions = [
                {"type": "gesture", "name": "wave"},
                {"type": "movement", "name": "forward", "distance": 1.0},
                {"type": "gesture", "name": "nod"},
                {"type": "system", "name": "sit_down"}
            ]
            
            result = executor.execute_sequence(actions)
            print(f"成功执行 {result} 个动作")
        
        错误处理:
            - 无效的动作格式（不是字典）: 记录错误并跳过
            - 缺少type字段: 使用默认值"gesture"
            - 缺少name字段: 尝试使用"action"字段作为备选
            - 单个动作执行失败: 继续执行下一个动作
        
        特点:
            - 容错性强：一个动作失败不会影响其他动作
            - 返回成功计数，便于监控执行情况
        """
        successful = 0
        
        for i, action in enumerate(actions):
            if not isinstance(action, dict):
                logger.error(f"Invalid action at index {i}: {action}")
                continue
            
            action_type = action.get("type", "gesture")
            action_name = action.get("name", action.get("action"))
            kwargs = {k: v for k, v in action.items() if k not in ["type", "name", "action"]}
            
            if self.execute(action_type, action_name, **kwargs):
                successful += 1
        
        logger.info(f"Action sequence completed: {successful}/{len(actions)} successful")
        return successful
    
    def get_available_actions(self) -> Dict[str, list]:
        """
        获取所有可用的动作
        
        功能:
            - 查询系统中所有可用的动作
            - 包括内置的三种动作类型
            - 不包括自定义处理器（因为自定义动作取决于用户定义）
        
        返回:
            字典，格式为：
            {
                "gesture": ["wave", "nod", "shake_head", ...],
                "movement": ["forward", "backward", "left", ...],
                "system": ["stand_up", "sit_down", "reset", ...]
            }
        
        例子:
            executor = get_executor()
            available = executor.get_available_actions()
            
            # 查看所有可用的手势
            print(available["gesture"])
            # ['wave', 'nod', 'shake_head', 'thumbs_up', 'bow', 'shrug']
            
            # 查看所有可用的运动
            print(available["movement"])
            # ['forward', 'backward', 'left', 'right', 'turn_left', ...]
        
        说明:
            使用各个模块的GESTURES、MOVEMENTS、SYSTEM_COMMANDS字典获取列表。
            如果模块中新增了新动作，这个函数会自动返回最新的列表。
        """
        return {
            "gesture": list(gesture.GESTURES.keys()),
            "movement": list(movement.MOVEMENTS.keys()),
            "system": list(system.SYSTEM_COMMANDS.keys()),
        }

    def cancel(self, action_id: str) -> bool:
        """Cancel a running async action by its action_id."""
        with self._lock:
            info = self.running_actions.get(action_id)
            if not info:
                logger.warning(f"No running action with id: {action_id}")
                return False
            cancel_event = info.get("cancel_event")
            if cancel_event:
                cancel_event.set()
            return True

    def cancel_all(self) -> int:
        """Cancel all running async actions. Returns number of cancelled actions."""
        with self._lock:
            ids = list(self.running_actions.keys())
        cancelled = 0
        for act_id in ids:
            if self.cancel(act_id):
                cancelled += 1
        logger.info(f"Cancelled {cancelled} running actions")
        return cancelled


# 全局执行器实例
_executor: Optional[ActionExecutor] = None


def get_executor() -> ActionExecutor:
    """
    获取或创建全局动作执行器实例
    
    说明:
        - 使用单例模式确保全局只有一个ActionExecutor实例
        - 第一次调用时创建实例
        - 后续调用返回同一实例
        - 这样可以保证所有动作共享同一个execution_history
    
    返回:
        ActionExecutor实例
    
    例子:
        executor = get_executor()
        executor.execute("gesture", "wave")
    """
    global _executor
    if _executor is None:
        _executor = ActionExecutor()
    return _executor


def execute(action_type: str, action_name: str, **kwargs) -> bool:
    """
    便利函数 - 直接执行动作（无需先获取执行器实例）
    
    说明:
        - 这是对get_executor().execute()的简化包装
        - 适合简单的一次性动作执行
    
    参数:
        action_type: 动作类型（gesture, movement, system 等）
        action_name: 动作名称
        **kwargs: 额外的参数（例如distance）
        
    返回:
        True - 动作执行成功
        False - 动作执行失败
    
    例子:
        execute("gesture", "wave")
        execute("movement", "forward", distance=1.5)
    """
    return get_executor().execute(action_type, action_name, **kwargs)
