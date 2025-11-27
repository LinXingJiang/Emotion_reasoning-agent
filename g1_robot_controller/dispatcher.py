"""
dispatcher.py - 响应分发器

功能说明:
    这个模块负责将Thor推理结果进行分类和路由到不同的处理器:
    1. Speech（语音）- 通过TTS扬声器输出文本
    2. Gesture（手势）- 执行面部和身体手势
    3. Movement（移动）- 执行机器人运动（走、转等）
    4. System（系统）- 执行系统命令（站起、坐下等）

主要数据流:
    Thor响应 → Dispatcher.dispatch() → _route_action()
         ↓
    根据action_type选择合适的处理器
         ↓
    执行具体动作（说话、做手势、移动等）

核心特性:
    - 支持自定义处理器注册（register_handler）
    - 支持单个或多个动作序列
    - 自动语言检测（中文/英文）
    - 错误处理和日志记录
"""

import logging
from typing import Callable, Dict, Any, Optional

from .speech.speaker import get_speaker
from .actions.gesture import execute_gesture
from .actions.movement import execute_movement
from .actions.system import execute_system_command
from .actions.action_executor import get_executor

logger = logging.getLogger(__name__)


class Dispatcher:
    """
    响应分发器 - 将Thor的推理结果路由到相应的处理器
    
    职责:
        1. 解析Thor返回的响应对象
        2. 根据action_type（说话、手势、移动、系统）分类
        3. 调用相应的处理器执行动作
        4. 支持自定义处理器扩展
    
    数据流程:
        Thor响应: {
            "text": "你好",              # 要说的话
            "action": "wave",           # 要做的动作名称
            "action_type": "gesture",   # 动作类型（gesture/movement/system）
            "actions": [...]            # 可选：动作序列
        }
        ↓
        Dispatcher分析response
        ↓
        调用_handle_speech()说话
        调用_route_action()执行动作
    
    支持的action_type:
        - "speech": 语音输出（通过TTS）
        - "gesture": 手势动作（wave, nod, shake_head等）
        - "movement": 机器人移动（forward, backward, turn等）
        - "system": 系统命令（stand_up, sit_down, reset等）
    """

    def __init__(self):
        """
        初始化分发器
        
        初始化内容:
            - handlers: 内置处理器映射（speech, gesture, movement, system）
            - custom_handlers: 自定义处理器字典（用户可以注册新的处理器）
        
        例子:
            dispatcher = Dispatcher()
            # 此时dispatcher已经有4个内置处理器
        """
        self.handlers: Dict[str, Callable] = {
            "speech": self._handle_speech,
            "gesture": self._handle_gesture,
            "movement": self._handle_movement,
            "system": self._handle_system,
        }
        self.custom_handlers: Dict[str, Callable] = {}

    def register_handler(self, action_type: str, handler: Callable) -> None:
        """
        注册自定义处理器
        
        说明:
            - 允许用户扩展Dispatcher支持的动作类型
            - 自定义处理器会优先于内置处理器被调用
        
        参数:
            action_type: 动作类型标识（例如 "custom_action"）
            handler: 处理函数（接受 action_name 和 context 参数）
        
        例子:
            def my_custom_handler(action_name, context):
                print(f"执行自定义动作: {action_name}")
            
            dispatcher.register_handler("custom", my_custom_handler)
        """
        self.custom_handlers[action_type] = handler
        logger.info(f"Registered custom handler for: {action_type}")

    def dispatch(self, response: Dict[str, Any]) -> bool:
        """
        分发Thor的响应到相应的处理器
        
        工作流程:
            1. 验证response是否为字典格式
            2. 如果有text字段，调用_handle_speech()输出语音
            3. 如果有action字段，调用_route_action()执行单个动作
            4. 如果有actions字段，循环处理多个动作序列
            5. 返回成功/失败状态
        
        参数:
            response: Thor返回的响应字典，可能包含：
                {
                    "text": "说的话",
                    "action": "hand_gesture_name",
                    "action_type": "gesture",
                    "actions": [
                        {"type": "gesture", "name": "wave"},
                        {"type": "movement", "name": "forward"}
                    ]
                }
        
        返回:
            True - 分发成功
            False - 分发失败（会记录错误日志）
        
        例子:
            response = {"text": "你好", "action": "wave", "action_type": "gesture"}
            dispatcher.dispatch(response)  # 会说话并做wave手势
        """
        if not isinstance(response, dict):
            logger.error(f"Invalid response format: {response}")
            return False

        try:
            # Handle speech response
            if "text" in response and response["text"]:
                self._handle_speech(response["text"], response)

            # Handle primary action if specified
            if "action" in response and response["action"]:
                action_type = response.get("action_type", "gesture")
                self._route_action(action_type, response["action"], response)

            # Handle additional actions if specified
            if "actions" in response and isinstance(response["actions"], list):
                for action_info in response["actions"]:
                    if isinstance(action_info, dict):
                        action_type = action_info.get("type", "gesture")
                        action_name = action_info.get("name", action_info.get("action"))
                        self._route_action(action_type, action_name, action_info)

            return True

        except Exception as e:
            logger.error(f"Error dispatching response: {e}")
            return False

    def _route_action(self, action_type: str, action_name: str, context: Dict[str, Any]) -> bool:
        """
        根据动作类型路由到相应的处理器
        
        路由逻辑:
            1. 首先检查自定义处理器（custom_handlers）
            2. 如果没有自定义处理器，查找内置处理器
            3. 调用对应的处理器函数
            4. 捕获异常并记录错误
        
        参数:
            action_type: 动作类型（"gesture", "movement", "system" 等）
            action_name: 具体动作名称（例如 "wave", "forward" 等）
            context: 包含额外信息的上下文字典
        
        返回:
            True - 路由并执行成功
            False - 路由失败或找不到对应处理器
        
        例子:
            _route_action("gesture", "wave", {})  # 执行wave手势
            _route_action("movement", "forward", {})  # 向前移动
        """
        # Check custom handlers first
        if action_type in self.custom_handlers:
            try:
                self.custom_handlers[action_type](action_name, context)
                return True
            except Exception as e:
                logger.error(f"Custom handler error: {e}")
                return False

        # Route to built-in handlers using central ActionExecutor
        try:
            # Prepare kwargs from context, filtering out routing fields
            kwargs = {k: v for k, v in context.items() if k not in ("type", "name", "action", "action_type", "text", "timestamp", "status")}
            executor = get_executor()
            exec_result = executor.execute(action_type, action_name, run_async=True, **kwargs)
            # If exec_result is string, it's an async action id
            if exec_result:
                if isinstance(exec_result, str):
                    logger.info(f"Started async action {action_type}:{action_name} (id={exec_result})")
                return True
            # If executor cannot handle (shouldn't happen), fallback to direct handler
        except Exception as e:
            logger.error(f"Executor error for {action_type}: {e}")
            # Continue to fallback

        handler = self.handlers.get(action_type)
        if handler:
            try:
                handler(action_name, context)
                return True
            except Exception as e:
                logger.error(f"Handler error for {action_type}: {e}")
                return False

        logger.warning(f"No handler found for action type: {action_type}")
        return False

    def _handle_speech(self, text: str, context: Optional[Dict] = None) -> bool:
        """
        处理语音输出
        
        功能:
            1. 获取全局TTS扬声器实例
            2. 从context中检测语言类型（自动判断中文或英文）
            3. 调用speaker.speak()输出语音
            4. 记录日志
        
        参数:
            text: 要说的文本内容
            context: 可选的上下文信息，可能包含：
                - "language": "en" 或 "zh"（用于语言选择）
        
        返回:
            True - 语音输出成功
            False - 语音输出失败
        
        例子:
            _handle_speech("你好，我是G1机器人", {"language": "zh"})
            _handle_speech("Hello, I am G1 robot", {"language": "en"})
        """
        try:
            speaker = get_speaker()
            
            # Detect language from context if available
            speaker_id = None
            if context and "language" in context:
                speaker_id = 1 if context["language"] == "en" else 0
            
            success = speaker.speak(text, speaker_id)
            
            if success:
                logger.info(f"✓ Speech output: {text}")
            else:
                logger.error(f"✗ Failed to speak: {text}")
            
            return success

        except Exception as e:
            logger.error(f"Speech handler error: {e}")
            return False

    def _handle_gesture(self, gesture_name: str, context: Optional[Dict] = None) -> bool:
        """
        处理手势执行
        
        功能:
            - 调用execute_gesture()函数执行指定的手势动作
            - 支持的手势: wave（挥手）, nod（点头）, shake_head（摇头）等
            - 记录执行日志
        
        参数:
            gesture_name: 手势名称（例如 "wave", "nod"）
            context: 可选上下文信息（当前未使用，保留以供扩展）
        
        返回:
            True - 手势执行成功
            False - 手势执行失败
        
        例子:
            _handle_gesture("wave")  # 机器人挥手
            _handle_gesture("nod")   # 机器人点头
        """
        try:
            # This would call the gesture action executor
            # For now, we just log it
            logger.info(f"Executing gesture: {gesture_name}")
            execute_gesture(gesture_name)
            return True
        except Exception as e:
            logger.error(f"Gesture handler error: {e}")
            return False

    def _handle_movement(self, movement_name: str, context: Optional[Dict] = None) -> bool:
        """
        处理机器人运动执行
        
        功能:
            - 调用execute_movement()函数执行机器人运动
            - 支持的运动: forward（前进）, backward（后退）, turn_left（左转）等
            - 记录执行日志
        
        参数:
            movement_name: 运动名称（例如 "forward", "backward", "turn_left"）
            context: 可选上下文信息（例如速度、距离等参数）
        
        返回:
            True - 运动执行成功
            False - 运动执行失败
        
        例子:
            _handle_movement("forward")    # 机器人前进
            _handle_movement("turn_left")  # 机器人左转
        """
        try:
            logger.info(f"Executing movement: {movement_name}")
            execute_movement(movement_name)
            return True
        except Exception as e:
            logger.error(f"Movement handler error: {e}")
            return False

    def _handle_system(self, command: str, context: Optional[Dict] = None) -> bool:
        """
        处理系统命令执行
        
        功能:
            - 调用execute_system_command()函数执行系统级命令
            - 支持的命令: stand_up（站起）, sit_down（坐下）, reset（复位）等
            - 通常用于机器人姿态控制
            - 记录执行日志
        
        参数:
            command: 系统命令名称（例如 "stand_up", "sit_down", "reset"）
            context: 可选上下文信息（当前未使用，保留以供扩展）
        
        返回:
            True - 命令执行成功
            False - 命令执行失败
        
        例子:
            _handle_system("stand_up")  # 机器人站起来
            _handle_system("sit_down")  # 机器人坐下
            _handle_system("reset")     # 机器人复位
        """
        try:
            logger.info(f"Executing system command: {command}")
            execute_system_command(command)
            return True
        except Exception as e:
            logger.error(f"System handler error: {e}")
            return False


# Global dispatcher instance
_dispatcher: Optional[Dispatcher] = None


def get_dispatcher() -> Dispatcher:
    """
    获取或创建全局分发器实例
    
    说明:
        - 使用单例模式确保全局只有一个Dispatcher实例
        - 第一次调用时创建实例，后续调用返回同一实例
        - 线程安全（ROS2回调会在不同线程调用，但创建后不会再修改）
    
    返回:
        Dispatcher实例
    
    例子:
        dispatcher = get_dispatcher()
        dispatcher.dispatch(response)
    """
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = Dispatcher()
    return _dispatcher


def dispatch(response: Dict[str, Any]) -> bool:
    """
    便利函数 - 直接分发响应（无需先获取Dispatcher实例）
    
    说明:
        - 这是一个快捷函数，内部调用get_dispatcher().dispatch()
        - 适合简单的一次性分发操作
    
    参数:
        response: Thor返回的响应字典
        
    返回:
        True - 分发成功
        False - 分发失败
    
    例子:
        response = {"text": "你好", "action": "wave", "action_type": "gesture"}
        dispatch(response)
    """
    return get_dispatcher().dispatch(response)
