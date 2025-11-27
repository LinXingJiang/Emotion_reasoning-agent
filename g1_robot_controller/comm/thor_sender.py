"""
thor_sender.py - Thor发送器

功能说明:
    这个模块负责将ASR语音识别结果和摄像头图像发送到Jetson Thor服务器
    进行VLM（视觉语言模型）推理。Thor服务器会理解用户的语音和当前
    环境图像，然后返回机器人应该执行的动作。

主要数据流:
    ASR文本 + 图像 → ThorSender.send_asr_with_image()
         ↓
    自动拍照（如果未提供图像路径）
         ↓
    Base64编码图像 + 构建JSON消息
         ↓
    通过ROS2发布到Thor话题
         ↓
    等待Thor返回推理结果

核心特性:
    1. 自动图像捕获 - 如果未提供图像，自动使用摄像头拍照
    2. Base64编码 - 将图像编码为Base64格式便于传输
    3. JSON序列化 - 支持灵活的消息结构
    4. 元数据支持 - 可以添加额外的自定义字段
    5. 单例模式 - 全局只有一个发送器实例

使用例子:
    sender = get_thor_sender()
    sender.send_asr_with_image("用户说的话")  # 自动拍照并发送
    sender.send_asr_with_image("话", image_path="photo.jpg")  # 使用指定图像
"""

import json
import time
import logging
import base64
import uuid
from typing import Optional, Dict, Any

from unitree_sdk2py.core.channel import ChannelPublisher
from unitree_sdk2py.idl.std_msgs.msg.dds_._String_ import String_

from ..utils import config
from ..sensors.camera_reader import capture_image

logger = logging.getLogger(__name__)


class ThorSender:
    """
    Thor发送器 - 将数据发送给Jetson Thor进行VLM推理
    
    核心职责:
        1. 与Jetson Thor建立ROS2通信
        2. 编码和打包ASR文本与图像数据
        3. 发送JSON格式的消息到Thor
        4. 支持自动图像捕获和编码
    
    通信协议:
        - 使用ROS2 String消息
        - 消息内容为JSON格式
        - 发送话题: config.THOR_SEND_TOPIC
    
    消息格式:
        {
            "asr_text": "用户说的话",
            "image_base64": "...",       # Base64编码的图像
            "image_path": "/path/to/img",
            "timestamp": null,
            "metadata": {...}            # 可选的额外字段
        }
    
    工作流程:
        初始化 → send_asr_with_image()
            ↓
        检查是否提供了图像路径
            ↓
        如果未提供，自动拍照（capture_image()）
            ↓
        将图像编码为Base64
            ↓
        构建JSON消息
            ↓
        通过ROS2发布器发送
            ↓
        记录日志和返回状态
    
    资源管理:
        - 初始化时创建ROS2发布器
        - 单例模式确保全局只有一个实例
        - 通过get_thor_sender()获取实例
    """

    def __init__(self):
        """
        初始化Thor发送器
        
        初始化的属性:
            publisher: ROS2发布器实例（最初为None）
            _initialized: 标记是否已初始化（False）
        
        说明:
            - 构造函数不会立即建立与Thor的连接
            - 必须调用initialize()才能实际初始化
            - 这样设计便于延迟初始化和错误处理
        """
        self.publisher: Optional[ChannelPublisher] = None
        self._initialized = False

    def initialize(self) -> None:
        """
        初始化发布器（与Thor建立通信）
        
        初始化步骤:
            1. 创建ChannelPublisher实例
            2. 指定发送话题（config.THOR_SEND_TOPIC）
            3. 指定消息类型（String_）
            4. 调用Init()完成初始化
            5. 设置_initialized标志为True
            6. 记录成功日志
        
        异常处理:
            - 如果任何步骤失败，捕获异常并记录错误日志
            - 然后重新抛出异常（调用者需要处理）
        
        说明:
            - 这个方法必须在调用send_asr_with_image()之前调用
            - 通常由get_thor_sender()自动调用
            - 只需调用一次
        
        例子:
            sender = ThorSender()
            sender.initialize()  # 初始化
            sender.send_asr_with_image("你好")  # 现在可以发送
        """
        try:
            self.publisher = ChannelPublisher(config.THOR_SEND_TOPIC, String_)
            self.publisher.Init()
            self._initialized = True
            logger.info(f"📤 Thor sender initialized on topic: {config.THOR_SEND_TOPIC}")
        except Exception as e:
            logger.error(f"Failed to initialize Thor sender: {e}")
            raise

    def _encode_image(self, image_path: str) -> Optional[str]:
        """
        将图像文件编码为Base64字符串
        
        工作流程:
            1. 打开指定路径的图像文件（二进制模式）
            2. 读取文件内容为字节数据
            3. 使用Base64编码
            4. 转换为UTF-8字符串
            5. 返回编码结果
        
        参数:
            image_path: 图像文件的路径（例如 "/tmp/photo.jpg"）
        
        返回:
            成功: Base64编码的字符串（可以嵌入到JSON）
            失败: None（会记录错误日志）
        
        异常处理:
            - 文件不存在: 捕获异常并返回None
            - 读取权限不足: 捕获异常并返回None
            - 其他IO错误: 捕获异常并返回None
        
        例子:
            b64_str = sender._encode_image("/tmp/photo.jpg")
            if b64_str:
                print(f"编码长度: {len(b64_str)} 字符")
        
        说明:
            Base64编码会使文件大小增加约33%，但便于在JSON中传输。
        """
        try:
            with open(image_path, "rb") as f:
                image_data = f.read()
            return base64.b64encode(image_data).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to encode image: {e}")
            return None

    def send_asr_with_image(
        self,
        asr_text: str,
        image_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        发送ASR文本和图像给Thor进行推理
        
        工作流程:
            1. 检查发送器是否已初始化
            2. 如果未提供image_path，自动调用capture_image()拍照
            3. 如果拍照失败，继续发送（仅包含文本）
            4. 将提供的图像路径编码为Base64
            5. 构建JSON消息，包含:
               - asr_text: 语音识别的文本
               - image_base64: Base64编码的图像（如有）
               - image_path: 原始图像路径
               - metadata: 额外的自定义字段（如有）
            6. 通过ROS2发布器发送到Thor
            7. 记录发送日志
        
        参数:
            asr_text: 从ASR模块获得的语音识别结果文本
            image_path: 可选的图像文件路径
                       - 如果为None，自动调用capture_image()拍照
                       - 如果拍照失败，只发送文本（不包含图像）
                       - 示例: "/tmp/photo.jpg"
            metadata: 可选的额外元数据字典
                     将被合并到JSON消息中
                     示例: {"emotion": "happy", "context": "greeting"}
        
        返回:
            True - 消息发送成功
            False - 发送失败（会记录错误日志）
        
        错误情况处理:
            - 发送器未初始化: 记录错误并返回False
            - 图像编码失败: 警告日志，继续发送文本部分
            - JSON序列化失败: 异常捕获，返回False
            - ROS2发布失败: 异常捕获，返回False
        
        消息格式:
            {
                "asr_text": "用户说的话",
                "image_base64": "iVBORw0KGgoAAAANS...",  # Base64编码的图像
                "image_path": "/tmp/photo.jpg",
                "timestamp": null,
                "emotion": "happy",                        # 如果提供了metadata
                "context": "greeting"                      # 如果提供了metadata
            }
        
        例子:
            # 自动拍照并发送
            sender.send_asr_with_image("你好")
            
            # 使用指定的图像
            sender.send_asr_with_image("你好", image_path="/tmp/my_photo.jpg")
            
            # 添加元数据
            sender.send_asr_with_image(
                "你好",
                metadata={"emotion": "happy", "gesture": "wave"}
            )
        """
        if not self._initialized:
            logger.error("Thor sender not initialized. Call initialize() first.")
            return False

        try:
            # Capture image if not provided
            if image_path is None:
                result = capture_image()
                if result is None:
                    logger.warning("Failed to capture image, sending ASR only")
                    image_path = None
                else:
                    image_path = result[1]
            
            # Prepare message
            message = {
                "asr_text": asr_text,
                # 同时提供 text 字段以便Thor处理方统一读取
                "text": asr_text,
                "timestamp": time.time(),  # 发送时间戳（秒）
                # 唯一请求标识，便于日志关联
                "request_id": str(uuid.uuid4()),
                "device_id": getattr(config, "NETWORK_INTERFACE", None)
            }

            # Add image if available
            if image_path:
                image_b64 = self._encode_image(image_path)
                if image_b64:
                    message["image_base64"] = image_b64
                    message["image_path"] = image_path
                    logger.info(f"Image encoded: {len(image_b64)} bytes")

            # Add metadata if provided, but avoid overriding core keys
            if metadata and isinstance(metadata, dict):
                for k, v in metadata.items():
                    if k in ("text", "asr_text", "timestamp", "image_base64", "image_path"):
                        continue
                    message[k] = v

            # Convert to JSON and send
            json_str = json.dumps(message)
            ros_msg = String_()
            ros_msg.data = json_str

            self.publisher.Write(ros_msg)
            
            logger.info(f"📤 Sent to Thor: '{asr_text}' with image")
            return True

        except Exception as e:
            logger.error(f"Failed to send to Thor: {e}")
            return False

    def send_raw_message(self, message: Dict[str, Any]) -> bool:
        """
        发送原始JSON消息给Thor
        
        说明:
            - 这是一个低级接口，直接发送自定义消息
            - 用于send_asr_with_image()不能满足的场景
            - 调用者完全负责消息格式的正确性
        
        参数:
            message: 要发送的消息字典
                    会被转换为JSON字符串后发送
                    示例: {"command": "stop", "priority": "high"}
        
        返回:
            True - 发送成功
            False - 发送失败（会记录错误日志）
        
        错误情况:
            - 发送器未初始化: 记录错误并返回False
            - JSON序列化失败: 异常捕获，记录错误，返回False
            - ROS2发布失败: 异常捕获，记录错误，返回False
        
        例子:
            sender.send_raw_message({"command": "pause"})
            sender.send_raw_message({
                "type": "query",
                "content": "What do you see?"
            })
        """
        if not self._initialized:
            logger.error("Thor sender not initialized. Call initialize() first.")
            return False

        try:
            json_str = json.dumps(message)
            ros_msg = String_()
            ros_msg.data = json_str
            
            self.publisher.Write(ros_msg)
            logger.debug(f"Sent raw message: {json_str}")
            return True

        except Exception as e:
            logger.error(f"Failed to send raw message: {e}")
            return False

    def close(self) -> None:
        """
        关闭Thor发送器并释放资源（如果适用）
        """
        try:
            # 如果publisher有额外的关闭或销毁方法，可在此调用
            self.publisher = None
            self._initialized = False
            logger.info("Thor sender closed")
        except Exception as e:
            logger.warning(f"Failed to close Thor sender: {e}")


# Global sender instance
_sender: Optional[ThorSender] = None


def get_thor_sender() -> ThorSender:
    """
    获取或创建全局Thor发送器实例
    
    说明:
        - 使用单例模式确保全局只有一个ThorSender实例
        - 第一次调用时创建实例并初始化
        - 后续调用返回同一实例
        - 这样可以保证与Thor的连接只建立一次
    
    返回:
        已初始化的ThorSender实例
    
    例子:
        sender = get_thor_sender()
        sender.send_asr_with_image("你好")
    """
    global _sender
    if _sender is None:
        _sender = ThorSender()
        _sender.initialize()
    return _sender


def send_to_thor(asr_text: str, image_path: Optional[str] = None) -> bool:
    """
    便利函数 - 直接发送ASR文本给Thor（无需先获取实例）
    
    说明:
        - 这是一个快捷函数，调用get_thor_sender().send_asr_with_image()
        - 适合简单的一次性发送操作
    
    参数:
        asr_text: 要发送的语音识别文本
        image_path: 可选的图像路径
                   如果为None，自动拍照
    
    返回:
        True - 发送成功
        False - 发送失败
    
    例子:
        send_to_thor("你好")  # 自动拍照并发送
        send_to_thor("你好", image_path="/tmp/photo.jpg")
    """
    return get_thor_sender().send_asr_with_image(asr_text, image_path)
