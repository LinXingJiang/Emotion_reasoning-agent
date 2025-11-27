"""
asr_listener.py - ASR（自动语音识别）监听器

功能说明:
    这个模块负责订阅G1机器人音频系统的ASR消息，并将JSON格式的语音数据
    解析为Python字典，然后传递给回调函数处理。

主要工作流程:
    1. 通过ROS2 DDS订阅ASR_TOPIC话题
    2. 接收来自机器人音频系统的语音识别结果
    3. 将JSON字符串解析为字典
    4. 验证必需字段（text, confidence, angle）
    5. 调用用户提供的回调函数处理数据

消息格式（JSON）:
    {
        "text": "用户说的话",          # 识别出的文本内容
        "confidence": 0.95,            # 置信度（0.0-1.0）
        "angle": 45.0                  # 声源角度（度数）
    }

核心特性:
    - 自动JSON解析和验证
    - 错误处理（无效JSON、缺少字段等）
    - 日志记录（包括置信度和角度信息）
    - 支持自定义回调函数
"""

import json
import logging
from typing import Callable, Optional

from unitree_sdk2py.core.channel import ChannelSubscriber
from unitree_sdk2py.idl.std_msgs.msg.dds_._String_ import String_

from ..utils import config

logger = logging.getLogger(__name__)


class ASRListener:
    """
    ASR监听器 - 订阅并处理G1机器人的语音识别结果
    
    功能:
        1. 订阅ROS2的ASR话题（默认 "asr"）
        2. 接收String_类型的ROS2消息
        3. 解析消息中的JSON数据
        4. 验证和提取关键信息（文本、置信度、角度）
        5. 调用回调函数处理ASR数据
    
    数据流:
        ROS2 String消息（JSON） → _on_asr_message() → JSON解析
            ↓
        字段验证 → 数据提取 → 调用callback(asr_data)
    
    期望的消息格式（JSON字符串）:
        {
            "text": "用户说的话",
            "confidence": 0.95,
            "angle": 45.0
        }
    
    返回格式（传给callback）:
        {
            "text": str,        # 识别的文本
            "confidence": float,  # 置信度 0.0-1.0
            "angle": float       # 角度（度数）
        }
    
    使用例子:
        def handle_asr(data):
            print(f"用户说: {data['text']}")
            print(f"置信度: {data['confidence']:.2f}")
        
        listener = ASRListener(handle_asr)
        listener.start()
        # 开始监听...
        listener.stop()
    """

    def __init__(self, callback: Callable[[dict], None]):
        """
        初始化ASR监听器
        
        参数:
            callback: 回调函数，当接收到ASR消息时被调用
                     回调函数签名: def callback(asr_data: dict) -> None
                     
                     asr_data参数包含:
                     {
                         "text": str,        # 用户说的话
                         "confidence": float,  # 置信度 0-1
                         "angle": float      # 声源角度
                     }
        
        例子:
            def on_speech(data):
                print(f"听到: {data['text']}")
            
            listener = ASRListener(on_speech)
        """
        self.callback = callback
        self.subscriber: Optional[ChannelSubscriber] = None

    def _on_asr_message(self, msg: String_) -> None:
        """
        处理接收到的ASR消息（ROS2回调函数）
        
        工作流程:
            1. 提取消息数据（处理字符串或可调用对象）
            2. 解析JSON格式的字符串
            3. 验证必需字段是否存在
            4. 提取text, confidence, angle字段
            5. 记录日志
            6. 调用用户回调函数
        
        参数:
            msg: ROS2 String_消息对象，包含JSON字符串数据
        
        异常处理:
            - JSON解析失败: 记录警告日志
            - 缺少'text'字段: 记录警告日志并返回
            - 其他字段缺失: 使用默认值（confidence=0.0, angle=0.0）
        
        例子:
            # 如果收到消息:
            # {"text": "你好", "confidence": 0.95, "angle": 30.0}
            # 日志会输出:
            # [ASR] User said: '你好' (confidence: 0.95, angle: 30.0°)
        """
        # Handle both string and callable data
        raw_data = msg.data if isinstance(msg.data, str) else msg.data()

        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse ASR JSON: {raw_data} - {e}")
            return

        # Validate required fields
        if "text" not in data:
            logger.warning(f"ASR message missing 'text' field: {data}")
            return

        # Extract data
        asr_data = {
            "text": data.get("text", ""),
            "confidence": data.get("confidence", 0.0),
            "angle": data.get("angle", 0.0),
        }

        logger.info(
            f"[ASR] User said: '{asr_data['text']}' "
            f"(confidence: {asr_data['confidence']:.2f}, angle: {asr_data['angle']:.1f}°)"
        )

        # Call the user-provided callback
        self.callback(asr_data)

    def start(self) -> None:
        """
        启动ASR监听
        
        功能:
            1. 创建ROS2频道订阅器（ChannelSubscriber）
            2. 订阅配置中指定的ASR话题（默认 "asr"）
            3. 设置回调函数 _on_asr_message
            4. 初始化订阅者
            5. 记录启动日志
        
        异常:
            如果订阅初始化失败，会捕获异常并重新抛出
        
        例子:
            listener = ASRListener(on_speech)
            listener.start()  # 现在开始接收ASR消息
            # 日志: 🎤 ASR listener started on topic: asr
        """
        try:
            self.subscriber = ChannelSubscriber(config.ASR_TOPIC, String_)
            self.subscriber.Init(self._on_asr_message)
            logger.info(f"🎤 ASR listener started on topic: {config.ASR_TOPIC}")
        except Exception as e:
            logger.error(f"Failed to initialize ASR listener: {e}")
            raise

    def stop(self) -> None:
        """
        停止ASR监听
        
        功能:
            - 释放ROS2订阅资源
            - 将subscriber设置为None
            - 记录停止日志
        
        说明:
            调用此方法后，监听器将停止接收ASR消息。
            如果需要再次监听，需要调用start()重新启动。
        """
        if self.subscriber:
            logger.info("ASR listener stopped")
            self.subscriber = None


# Convenience function for simple usage
def create_asr_listener(callback: Callable[[dict], None]) -> ASRListener:
    """
    便利函数 - 创建并启动ASR监听器
    
    功能:
        - 一次性创建和启动ASR监听器
        - 不需要分别调用 ASRListener() 和 listener.start()
    
    参数:
        callback: 处理ASR数据的回调函数
    
    返回:
        已启动的ASRListener实例
    
    例子:
        def on_speech(data):
            print(f"你说: {data['text']}")
        
        listener = create_asr_listener(on_speech)
        # 监听器已自动启动，开始接收消息
    """
    listener = ASRListener(callback)
    listener.start()
    return listener
