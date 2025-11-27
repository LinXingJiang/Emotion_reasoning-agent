"""
thor_listener.py - Thor监听器

功能说明:
    这个模块负责接收来自Jetson Thor服务器的推理结果。
    Thor根据用户语音和环境图像进行VLM推理，返回机器人应该
    执行的动作、要说的话、以及表达的情感等信息。

主要工作流程:
    1. 通过ROS2 DDS订阅THOR_RECV_TOPIC话题
    2. 接收来自Thor服务器的JSON格式推理结果
    3. 解析JSON数据
    4. 调用用户提供的回调函数处理响应
    5. 后续由Dispatcher路由到相应的动作执行器

Thor返回的数据格式:
    {
        "status": "success",           # 推理状态 (必需)
        "text": "机器人要说的话",      # 语音输出内容 (可选)
        "action": "wave",              # 要执行的动作名称 (可选)
        "action_type": "gesture",      # 动作类型 (可选: gesture/movement/system)
        "actions": [...],              # 动作序列 (可选, 与action互斥)
        "emotion": "happy",            # 机器人表达的情感 (可选)
        "confidence": 0.95,            # 推理置信度 (可选)
        "request_id": "uuid",          # 请求ID，用于追踪 (可选)
        "device_id": "eth0"            # 设备ID (可选)
    }
    
完整示例:
    单动作响应:
    {
        "status": "success",
        "text": "好的,我挥手了",
        "action": "wave",
        "action_type": "gesture",
        "emotion": "happy",
        "confidence": 0.98,
        "request_id": "550e8400-e29b-41d4-a716-446655440000"
    }
    
    动作序列响应:
    {
        "status": "success",
        "text": "让我演示一下",
        "actions": [
            {"type": "gesture", "name": "nod"},
            {"type": "movement", "name": "forward"},
            {"type": "gesture", "name": "wave"}
        ],
        "emotion": "confident",
        "confidence": 0.95
    }
    
    错误响应:
    {
        "status": "error",
        "text": "抱歉,我没理解",
        "error": "vision_model_timeout",
        "confidence": 0.0
    }

核心特性:
    - 自动JSON解析和验证
    - 错误处理（无效JSON等）
    - 日志记录
    - 支持自定义回调函数

使用例子:
    def handle_thor_response(data):
        print(f"Thor说: {data['text']}")
        print(f"动作: {data['action']}")
    
    listener = ThorListener(handle_thor_response)
    listener.start()
"""

import json
import logging
from typing import Callable, Optional

from unitree_sdk2py.core.channel import ChannelSubscriber
from unitree_sdk2py.idl.std_msgs.msg.dds_._String_ import String_

from ..utils import config

logger = logging.getLogger(__name__)


class ThorListener:
    """
    Thor监听器 - 接收并处理Jetson Thor的推理结果
    
    功能:
        1. 订阅ROS2的Thor响应话题
        2. 接收String_类型的ROS2消息
        3. 解析消息中的JSON推理结果
        4. 调用回调函数处理结果
    
    数据流:
        Jetson Thor推理 → ROS2发布 → ThorListener接收
            ↓
        JSON解析 → 回调函数处理 → Dispatcher路由
            ↓
        执行对应的动作（说话、手势、移动等）
    
    期望的消息格式（JSON字符串）:
        必需字段:
            "status": str  # "success" 或 "error"
        
        可选字段 (用于成功响应):
            "text": str               # 机器人要说的话
            "action": str             # 单个动作名称 (与actions互斥)
            "action_type": str        # 动作类型: gesture/movement/system
            "actions": list           # 动作序列 (与action互斥)
            "emotion": str            # 情感: happy/sad/neutral/confident等
            "confidence": float       # 置信度 0.0-1.0
            "request_id": str         # 请求追踪ID (UUID)
            "device_id": str          # 设备标识
        
        可选字段 (用于错误响应):
            "error": str              # 错误描述
            "text": str               # 错误说明文本
        
        完整示例见模块顶部的文档字符串。
    
    返回格式（传给callback）:
        与接收到的JSON完全相同（已解析为Python字典）
    
    使用例子:
        def on_thor_response(data):
            print(f"状态: {data['status']}")
            print(f"说: {data['text']}")
            print(f"动作: {data['action']}")
        
        listener = ThorListener(on_thor_response)
        listener.start()
        # 开始监听Thor响应...
        listener.stop()
    
    生命周期:
        创建 → start()开始监听 → 接收消息 → 调用回调
              → stop()停止监听 → 释放资源
    """

    def __init__(self, callback: Callable[[dict], None]):
        """
        初始化Thor监听器
        
        参数:
            callback: 回调函数，当接收到Thor响应时被调用
                     回调函数签名: def callback(response_data: dict) -> None
                     
                     response_data参数包含:
                     {
                         "status": str,        # 推理状态
                         "text": str,          # 要说的话
                         "action": str,        # 动作名称
                         "action_type": str,   # 动作类型
                         "emotion": str,       # 情感
                         "confidence": float   # 置信度
                     }
        
        例子:
            def on_response(data):
                dispatcher.dispatch(data)  # 路由到dispatcher
            
            listener = ThorListener(on_response)
        """
        self.callback = callback
        self.subscriber: Optional[ChannelSubscriber] = None

    def _on_thor_message(self, msg: String_) -> None:
        """
        处理接收到的Thor响应消息（ROS2回调函数）
        
        工作流程:
            1. 提取消息数据（处理字符串或可调用对象）
            2. 解析JSON格式的字符串
            3. 验证必需字段 (status)
            4. 记录接收日志
            5. 调用用户回调函数进行处理
        
        参数:
            msg: ROS2 String_消息对象，包含JSON字符串数据
        
        消息验证:
            - 必须包含 "status" 字段
            - status可以是 "success" 或 "error"
            - 如果缺少status，记录警告并跳过
        
        异常处理:
            - JSON解析失败: 记录警告日志并返回
            - 缺少必需字段: 记录警告日志并返回
            - 回调函数异常: 记录错误但不中断监听
        
        例子:
            # 如果收到消息:
            # {"status": "success", "text": "你好", "action": "wave", "request_id": "..."}
            # 日志会输出:
            # [THOR] Response received (request_id=...): {'status': 'success', ...}
            # 然后调用回调函数处理该数据
        """
        # Handle both string and callable data
        raw_data = msg.data if isinstance(msg.data, str) else msg.data()

        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Thor JSON: {raw_data} - {e}")
            return

        # Validate required fields
        if "status" not in data:
            logger.warning(f"Thor response missing required 'status' field: {data}")
            return

        # Extract request_id for logging if available
        request_id = data.get("request_id", "unknown")
        status = data.get("status")
        
        if status == "error":
            error_msg = data.get("error", "unknown_error")
            logger.warning(f"[THOR] Error response (request_id={request_id}): {error_msg}")
        else:
            logger.info(f"[THOR] Response received (request_id={request_id}): {data}")

        # Call the user-provided callback with error handling
        try:
            self.callback(data)
        except Exception as e:
            logger.error(f"Error in Thor response callback: {e}", exc_info=True)

    def start(self) -> None:
        """
        启动Thor监听
        
        功能:
            1. 创建ROS2频道订阅器（ChannelSubscriber）
            2. 订阅配置中指定的Thor响应话题（config.THOR_RECV_TOPIC）
            3. 设置回调函数 _on_thor_message
            4. 初始化订阅者
            5. 记录启动日志
        
        异常:
            如果订阅初始化失败，会捕获异常并重新抛出
        
        例子:
            listener = ThorListener(on_response)
            listener.start()  # 现在开始接收Thor消息
            # 日志: 📥 Thor listener started on topic: thor_response
        """
        try:
            self.subscriber = ChannelSubscriber(config.THOR_RECV_TOPIC, String_)
            self.subscriber.Init(self._on_thor_message)
            logger.info(f"📥 Thor listener started on topic: {config.THOR_RECV_TOPIC}")
        except Exception as e:
            logger.error(f"Failed to initialize Thor listener: {e}")
            raise

    def stop(self) -> None:
        """
        停止Thor监听
        
        功能:
            - 释放ROS2订阅资源
            - 将subscriber设置为None
            - 记录停止日志
        
        说明:
            调用此方法后，监听器将停止接收Thor消息。
            如果需要再次监听，需要调用start()重新启动。
        """
        if self.subscriber:
            logger.info("Thor listener stopped")
            self.subscriber = None


# Convenience function for simple usage
def create_thor_listener(callback: Callable[[dict], None]) -> ThorListener:
    """
    便利函数 - 创建并启动Thor监听器
    
    功能:
        - 一次性创建和启动Thor监听器
        - 不需要分别调用 ThorListener() 和 listener.start()
    
    参数:
        callback: 处理Thor响应的回调函数
    
    返回:
        已启动的ThorListener实例
    
    例子:
        def on_thor(data):
            print(f"Thor返回: {data}")
        
        listener = create_thor_listener(on_thor)
        # 监听器已自动启动，开始接收消息
    """
    listener = ThorListener(callback)
    listener.start()
    return listener
