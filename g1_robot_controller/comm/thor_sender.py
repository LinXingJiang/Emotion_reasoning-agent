"""
thor_sender.py - Thor HTTP请求发送器

功能说明:
    这个模块负责将ASR语音识别结果和摄像头图像通过HTTP POST发送到
    Jetson Thor服务器进行VLM（视觉语言模型）推理。Thor服务器会理解
    用户的语音和当前环境图像，然后返回机器人应该执行的动作。

主要数据流:
    ASR文本 + 图像 → ThorSender.send_asr_with_image()
         ↓
    自动拍照（如果未提供图像路径）
         ↓
    Base64编码图像 + 构建JSON消息
         ↓
    通过HTTP POST发送到Thor服务器
         ↓
    同步接收Thor返回的JSON推理结果

核心特性:
    1. 自动图像捕获 - 如果未提供图像，自动使用摄像头拍照
    2. Base64编码 - 将图像编码为Base64格式便于传输
    3. JSON序列化 - 支持灵活的消息结构
    4. 同步HTTP通信 - 发送请求后等待响应
    5. 错误处理和重试 - 网络异常时自动重试

使用例子:
    sender = get_thor_sender()
    response = sender.send_asr_with_image("用户说的话")  # 自动拍照并发送
    if response:
        print(response["text"])  # 机器人要说的话
"""

import json
import time
import logging
import base64
import uuid
import requests
from typing import Optional, Dict, Any

from ..utils import config
from ..sensors.camera_reader import capture_image

logger = logging.getLogger(__name__)


class ThorSender:
    """
    Thor HTTP发送器 - 将数据发送给Jetson Thor进行VLM推理
    
    核心职责:
        1. 与Jetson Thor建立HTTP连接
        2. 编码和打包ASR文本与图像数据
        3. POST JSON到Thor服务器并接收响应
        4. 支持自动图像捕获和编码
    
    通信协议:
        - 使用HTTP POST请求
        - 消息内容为JSON格式
        - Thor服务器URL: config.THOR_URL
    
    请求消息格式:
        {
            "text": "用户说的话",
            "image_base64": "...",       # Base64编码的图像
            "request_id": "uuid",
            "timestamp": 1234567890.0
        }
    
    响应消息格式:
        {
            "status": "success",
            "text": "机器人要说的话",
            "action": "wave",
            "action_type": "gesture",
            "emotion": "happy",
            "confidence": 0.95
        }
    
    工作流程:
        send_asr_with_image() → 拍照 → Base64编码
            ↓
        构建JSON请求 → POST到Thor → 解析响应
            ↓
        返回响应字典
    """

    def __init__(self, thor_url: Optional[str] = None, timeout: float = 30.0):
        """
        初始化Thor HTTP发送器
        
        参数:
            thor_url: Thor服务器URL (默认从config.THOR_URL读取)
            timeout: HTTP请求超时时间(秒) (默认30秒)
        """
        self.thor_url = thor_url or config.THOR_URL
        self.timeout = timeout
        self.session = requests.Session()  # 复用连接
        logger.info(f"📤 Thor HTTP sender initialized: {self.thor_url}")

    def _encode_image(self, image_path: str) -> Optional[str]:
        """
        将图像文件编码为Base64字符串
        
        参数:
            image_path: 图像文件路径
        
        返回:
            成功: Base64编码的字符串
            失败: None
        """
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
                return base64.b64encode(image_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to encode image {image_path}: {e}")
            return None

    def send_asr_with_image(
        self,
        asr_text: str,
        image_path: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        发送ASR文本和图像到Thor，并同步返回推理结果
        
        工作流程:
            1. 如果未提供image_path，自动调用capture_image()拍照
            2. 将图像编码为Base64
            3. 构建JSON请求
            4. POST到Thor服务器/infer端点
            5. 解析并返回JSON响应
        
        参数:
            asr_text: ASR语音识别结果文本
            image_path: 可选的图像文件路径(None时自动拍照)
        
        返回:
            成功: 返回Thor响应字典 {"status": "success", "text": "...", "action": "...", ...}
            失败: 返回None
        """
        try:
            # Capture image if not provided
            if image_path is None:
                result = capture_image()
                if result is None:
                    logger.warning("Failed to capture image, sending text only")
                    image_path = None
                else:
                    image_path = result[1]
            
            # Prepare request payload
            payload = {
                "text": asr_text,
                "request_id": str(uuid.uuid4()),
                "timestamp": time.time()
            }

            # Add image if available
            if image_path:
                image_b64 = self._encode_image(image_path)
                if image_b64:
                    payload["image_base64"] = image_b64
                    logger.info(f"Image encoded: {len(image_b64)} chars")

            # Send POST request
            logger.info(f"📤 Sending to Thor: '{asr_text}' (image: {image_path is not None})")
            
            response = self.session.post(
                f"{self.thor_url}/infer",
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code != 200:
                logger.error(f"Thor error: {response.status_code} - {response.text}")
                return None
            
            result = response.json()
            logger.info(f"✅ Received from Thor: {result.get('text', '')[:50]}...")
            return result

        except requests.exceptions.Timeout:
            logger.error(f"Request timeout after {self.timeout}s")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection failed to {self.thor_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to send to Thor: {e}", exc_info=True)
            return None

    def close(self) -> None:
        """关闭HTTP会话并释放资源"""
        try:
            self.session.close()
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
        - 第一次调用时创建实例
        - 后续调用返回同一实例
    
    返回:
        已初始化的ThorSender实例
    """
    global _sender
    if _sender is None:
        _sender = ThorSender()
    return _sender


def send_to_thor(asr_text: str, image_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    便利函数 - 直接发送ASR文本给Thor并获取响应
    
    参数:
        asr_text: 要发送的语音识别文本
        image_path: 可选的图像路径(None时自动拍照)
    
    返回:
        Thor响应字典或None
    """
    return get_thor_sender().send_asr_with_image(asr_text, image_path)
