"""
speaker.py - 文本转语音（TTS）模块

功能说明:
    这个模块提供文本转语音（TTS）功能，支持中英文自动检测和切换。
    通过Unitree SDK的AudioClient与机器人音频系统交互。

主要特性:
    1. 自动语言检测 - 根据文本自动选择中文或英文语音
    2. 灵活配置 - 支持手动指定语言或自动检测
    3. 单例模式 - 全局只有一个Speaker实例
    4. 错误处理 - 完善的异常捕获和日志记录

支持的语言:
    - 0: 中文（Chinese）
    - 1: 英文（English）

工作流程:
    text → 初始化AudioClient → 语言检测 → 调用TtsMaker → 机器人发音

例子:
    speaker = get_speaker()
    speaker.speak("你好，我是G1")      # 自动检测中文
    speaker.speak("Hello, I am G1")   # 自动检测英文
    speaker.speak_chinese("你好")      # 强制中文
    speaker.speak_english("Hello")    # 强制英文
"""

import logging
from typing import Optional

from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient

from ..utils import config

logger = logging.getLogger(__name__)


class Speaker:
    """
    G1机器人文本转语音扬声器
    
    核心功能:
        1. 与Unitree AudioClient交互
        2. 支持中文和英文语音
        3. 自动语言检测
        4. 错误处理和日志记录
    
    语言标识:
        - 0: 中文（Chinese）- 使用中文语音
        - 1: 英文（English）- 使用英文语音
    
    初始化:
        - 第一次创建时需要调用initialize()初始化AudioClient
        - initialize()会与机器人音频系统建立连接
        - 设置TTS超时时间（config.TTS_TIMEOUT）
    
    使用方式:
        方法1: 自动检测语言
            speaker.speak("你好")        # 检测为中文，用中文发音
            speaker.speak("Hello")       # 检测为英文，用英文发音
        
        方法2: 手动指定语言
            speaker.speak("你好", speaker=0)   # 强制中文
            speaker.speak("Hello", speaker=1)  # 强制英文
        
        方法3: 使用简化方法
            speaker.speak_chinese("你好")
            speaker.speak_english("Hello")
    
    语言检测算法:
        - 简单启发式方法：检查文本是否包含英文字母
        - 如果有英文字母 → speaker=1（英文）
        - 否则 → speaker=0（中文）
    """

    def __init__(self):
        """
        初始化Speaker对象
        
        初始化的属性:
            audio_client: AudioClient实例（最初为None）
            _initialized: 标记是否已初始化（False）
        
        说明:
            - 构造函数不会立即连接到音频系统
            - 必须调用initialize()才能实际初始化
            - 这样设计便于延迟初始化和错误处理
        """
        self.audio_client: Optional[AudioClient] = None
        self._initialized = False

    def initialize(self) -> None:
        """
        初始化音频客户端
        
        初始化步骤:
            1. 创建AudioClient实例
            2. 设置TTS超时时间（从config.TTS_TIMEOUT读取）
            3. 调用Init()方法进行初始化
            4. 设置_initialized标志为True
            5. 记录成功日志
        
        异常处理:
            - 如果任何步骤失败，捕获异常并记录错误日志
            - 然后重新抛出异常（调用者需要处理）
        
        说明:
            - 这个方法必须在调用speak()之前调用
            - 通常由get_speaker()自动调用
            - 只需调用一次（后续调用speak()会检查_initialized标志）
        
        例子:
            speaker = Speaker()
            speaker.initialize()  # 初始化
            speaker.speak("你好")  # 现在可以说话
        """
        try:
            self.audio_client = AudioClient()
            self.audio_client.SetTimeout(config.TTS_TIMEOUT)
            self.audio_client.Init()
            self._initialized = True
            logger.info("🔊 TTS speaker initialized")
        except Exception as e:
            logger.error(f"Failed to initialize TTS speaker: {e}")
            raise

    def _detect_language(self, text: str) -> int:
        """
        自动检测文本语言
        
        检测算法:
            1. 遍历文本中的每个字符
            2. 检查是否存在英文字母（a-z, A-Z）
            3. 如果存在至少一个英文字母 → 返回1（英文）
            4. 否则 → 返回0（中文）
        
        参数:
            text: 要分析的文本内容
        
        返回:
            0 - 中文
            1 - 英文
        
        说明:
            - 这是一个启发式方法，不是完全准确的语言检测
            - 对于混合内容（中英混合），会以是否包含英文字母为决定条件
            - 例如 "你好hello" 会被识别为英文，因为包含"hello"
        
        例子:
            _detect_language("你好")           # 返回0（中文）
            _detect_language("Hello")          # 返回1（英文）
            _detect_language("你好Hello")      # 返回1（混合，含英文）
        """
        # Check for English characters
        has_english = any("a" <= c.lower() <= "z" for c in text)
        
        # Simple heuristic: if text contains English letters, use English speaker
        # Otherwise use Chinese speaker
        return 1 if has_english else 0

    def speak(self, text: str, speaker: Optional[int] = None) -> bool:
        """
        说出给定的文本
        
        工作流程:
            1. 检查Speaker是否已初始化
            2. 验证文本有效性（非空、字符串类型）
            3. 如果未指定speaker，自动检测语言
            4. 记录日志（包括语言类型和文本内容）
            5. 调用audio_client.TtsMaker()进行语音合成
            6. 返回成功/失败状态
        
        参数:
            text: 要说的文本内容（必须是非空字符串）
            speaker: 可选的语音角色ID
                    None: 自动检测（默认）
                    0: 中文语音
                    1: 英文语音
        
        返回:
            True - 语音输出成功
            False - 语音输出失败（会记录错误日志）
        
        错误情况:
            - Speaker未初始化: 记录错误并返回False
            - 文本无效（为空或非字符串）: 记录警告并返回False
            - TtsMaker()调用异常: 捕获异常、记录错误并返回False
        
        例子:
            speaker = get_speaker()
            
            # 自动检测语言
            speaker.speak("你好")           # 检测为中文
            speaker.speak("Hello")          # 检测为英文
            
            # 手动指定语言
            speaker.speak("你好", speaker=0)   # 强制中文发音
            speaker.speak("Hello", speaker=1)  # 强制英文发音
        
        日志输出:
            成功: 🔊 Speaking (中文): 你好
            成功: 🔊 Speaking (English): Hello
            失败: Speaker not initialized...
        """
        if not self._initialized:
            logger.error("Speaker not initialized. Call initialize() first.")
            return False

        if not text or not isinstance(text, str):
            logger.warning(f"Invalid text for TTS: {text}")
            return False

        try:
            # Auto-detect language if not specified
            if speaker is None:
                speaker = self._detect_language(text)

            speaker_name = ["中文", "English"][min(speaker, 1)]
            logger.info(f"🔊 Speaking ({speaker_name}): {text}")

            self.audio_client.TtsMaker(text, speaker)
            return True

        except Exception as e:
            logger.error(f"TTS error: {e}")
            return False

    def speak_chinese(self, text: str) -> bool:
        """
        用中文发音说出文本
        
        说明:
            - 这是speak(text, speaker=0)的便利方法
            - 强制使用中文语音，不进行语言检测
        
        参数:
            text: 要说的中文文本
        
        返回:
            True - 成功
            False - 失败
        
        例子:
            speaker.speak_chinese("你好，机器人")
        """
        return self.speak(text, speaker=0)

    def speak_english(self, text: str) -> bool:
        """
        用英文发音说出文本
        
        说明:
            - 这是speak(text, speaker=1)的便利方法
            - 强制使用英文语音，不进行语言检测
        
        参数:
            text: 要说的英文文本
        
        返回:
            True - 成功
            False - 失败
        
        例子:
            speaker.speak_english("Hello, robot")
        """
        return self.speak(text, speaker=1)

    def close(self) -> None:
        """
        关闭音频客户端
        
        功能:
            - 释放与音频系统的连接
            - 设置_initialized标志为False
            - 记录关闭日志
        
        说明:
            关闭后，如果需要再次使用，必须调用initialize()重新初始化。
            通常在程序退出时调用。
        """
        if self.audio_client:
            try:
                # 尝试调用AudioClient的关闭/销毁方法（如有）
                if hasattr(self.audio_client, "Close"):
                    self.audio_client.Close()
                elif hasattr(self.audio_client, "Destroy"):
                    self.audio_client.Destroy()
                elif hasattr(self.audio_client, "UnInit"):
                    self.audio_client.UnInit()
            except Exception as e:
                logger.warning(f"Failed to shutdown audio client method: {e}")
            finally:
                try:
                    self.audio_client = None
                except Exception:
                    pass
                self._initialized = False
                logger.info("TTS speaker closed")


# Global speaker instance
_speaker: Optional[Speaker] = None


def get_speaker() -> Speaker:
    """
    获取或创建全局Speaker实例
    
    说明:
        - 使用单例模式确保全局只有一个Speaker实例
        - 第一次调用时创建实例并初始化
        - 后续调用返回同一实例
        - 这样可以保证与音频系统的连接只建立一次
    
    返回:
        已初始化的Speaker实例
    
    例子:
        speaker = get_speaker()
        speaker.speak("你好")
    """
    global _speaker
    if _speaker is None:
        _speaker = Speaker()
        _speaker.initialize()
    return _speaker


def speak(text: str, speaker: Optional[int] = None) -> bool:
    """
    便利函数 - 直接说出文本（无需先获取Speaker实例）
    
    说明:
        - 这是一个快捷函数，调用get_speaker().speak()
        - 适合简单的一次性语音输出
    
    参数:
        text: 要说的文本
        speaker: 可选的语音角色ID（0=中文, 1=英文）
        
    返回:
        True - 成功
        False - 失败
    
    例子:
        speak("你好")           # 自动检测中文
        speak("Hello")          # 自动检测英文
        speak("你好", speaker=0)  # 强制中文
    """
    return get_speaker().speak(text, speaker)
