"""
main.py - G1机器人控制器主入口程序

功能说明:
    这是整个G1机器人控制系统的主入口。负责：
    1. 初始化所有系统组件（ASR语音识别、TTS语音合成、摄像头、Thor通信等）
    2. 启动事件循环，保持系统运行
    3. 管理ASR消息 → Thor处理 → 响应分发的完整流程

工作流程:
    用户说话 → ASR捕获 → 发送给Thor → Thor返回结果 → 分发器路由 → 执行动作

使用方法:
    python -m g1_robot_controller eth0              # 启动系统
    python -m g1_robot_controller eth0 --debug      # 启动并显示调试信息
"""

import sys
import time
import logging
import argparse
from typing import Optional

# ROS2通信库
from unitree_sdk2py.core.channel import ChannelFactoryInitialize

# 本地模块导入
from .utils import config                           # 配置管理
from .sensors.asr_listener import ASRListener       # 语音识别监听器
from .comm.thor_sender import get_thor_sender       # Thor数据发送器
from .comm.thor_listener import ThorListener        # Thor响应监听器
from .dispatcher import get_dispatcher              # 响应分发器
from .speech.speaker import get_speaker             # 文本转语音

# ============================================================
# 日志配置 - 用于输出系统运行信息和错误诊断
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class G1RobotController:
    """
    G1机器人控制器 - 协调整个系统的核心类
    
    主要职责:
        1. 初始化所有子系统（ASR、TTS、摄像头、Thor通信、分发器）
        2. 管理系统事件循环
        3. 处理ASR语音输入回调
        4. 处理Thor推理结果回调
        5. 提供优雅的系统关闭
    
    数据流向:
        ASR语音输入 → _on_asr_data() → Thor发送器 → Jetson Thor处理
                                                      ↓
        分发器 ← Thor监听器 ← Jetson Thor返回结果
        ├→ 扬声器(TTS语音输出)
        ├→ 动作执行器(手势、移动、系统命令)
        └→ 自定义处理器(用户扩展)
    """

    def __init__(self, network_interface: str):
        """
        初始化机器人控制器
        
        参数:
            network_interface: 网络接口名称 (例如: 'eth0', 'wlan0')
                              用于ROS2 DDS通信
        """
        self.network_interface = network_interface
        self.running = False
        
        # 系统组件（延迟初始化）
        self.asr_listener: Optional[ASRListener] = None           # 语音识别监听器
        self.thor_sender = None                                   # Thor数据发送器
        self.thor_listener: Optional[ThorListener] = None         # Thor响应监听器
        self.dispatcher = None                                    # 响应分发器
        self.speaker = None                                       # 文本转语音

    def initialize(self) -> bool:
        """
        初始化所有系统组件
        
        初始化顺序:
            1. ROS2 DDS通信通道 - 实现机器人和计算机之间的消息传递
            2. TTS扬声器 - 负责机器人发出语音
            3. Thor发送器 - 将ASR和图像发送给Jetson Thor进行推理
            4. 响应分发器 - 路由Thor返回的推理结果
            5. ASR监听器 - 监听机器人麦克风的语音输入
            6. Thor监听器 - 监听Thor返回的推理结果
        
        返回:
            True: 初始化成功
            False: 初始化失败（检查日志了解详情）
        """
        try:
            logger.info("=" * 60)
            logger.info("🤖 G1 机器人控制器 - 正在初始化")
            logger.info("=" * 60)

            # 第1步：初始化ROS2 DDS通信 - 这是机器人和计算机通信的基础
            logger.info(f"📡 初始化ROS2 DDS，网络接口: {self.network_interface}")
            ChannelFactoryInitialize(0, self.network_interface)

            # 第2步：初始化TTS扬声器 - 让机器人能说话
            logger.info("🔊 初始化文本转语音(TTS)...")
            self.speaker = get_speaker()

            # 第3步：初始化Thor数据发送器 - 将数据发送给Jetson Thor
            logger.info("📤 初始化Thor数据发送器...")
            self.thor_sender = get_thor_sender()

            # 第4步：初始化响应分发器 - 决定如何处理Thor的返回结果
            logger.info("⚙️ 初始化响应分发器...")
            self.dispatcher = get_dispatcher()

            # 第5步：初始化ASR语音识别监听器 - 捕获用户说话
            logger.info("🎤 初始化语音识别(ASR)监听器...")
            self.asr_listener = ASRListener(self._on_asr_data)
            self.asr_listener.start()

            # 第6步：初始化Thor响应监听器 - 接收Jetson Thor的推理结果
            logger.info("📥 初始化Thor响应监听器...")
            self.thor_listener = ThorListener(self._on_thor_response)
            self.thor_listener.start()

            logger.info("=" * 60)
            logger.info("✅ 所有组件初始化成功！")
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            return False

    def _on_asr_data(self, asr_data: dict) -> None:
        """
        ASR语音识别回调函数 - 当用户说话时调用
        
        工作流程:
            1. 接收ASR数据 (文本、信心度、角度)
            2. 捕获摄像头图像
            3. 打包数据发送给Jetson Thor进行推理
            4. Thor会返回推理结果（说什么、做什么动作、情感等）
        
        参数:
            asr_data: 字典，包含:
                {
                    "text": "用户说的内容",
                    "confidence": 0.95,  # 识别信心度 (0-1)
                    "angle": 45.0        # 声源角度 (度)
                }
        """
        logger.info(f"[ASR回调] 接收到: {asr_data}")

        # 提取用户说的文本
        text = asr_data.get("text", "")
        if text:
            logger.info(f"📤 发送给Thor: '{text}' (附带图像)")
            # 调用Thor发送器，自动捕获图像并发送
            self.thor_sender.send_asr_with_image(text, metadata=asr_data)

    def _on_thor_response(self, response: dict) -> None:
        """
        Thor推理结果回调函数 - 当Thor返回推理结果时调用
        
        工作流程:
            1. 接收Thor返回的推理结果
            2. 分发器解析结果
            3. 路由到对应的处理器:
               - 如果有"text" → TTS扬声器播放回复
               - 如果有"action" → 动作执行器执行动作
               - 其他 → 自定义处理器处理
        
        参数:
            response: 字典，包含:
                {
                    "status": "success",
                    "text": "要说的话",
                    "action": "动作名称",
                    "action_type": "gesture|movement|system",
                    "emotion": "happy|sad|neutral|etc",
                    "confidence": 0.95
                }
        """
        logger.info(f"[Thor回调] 接收到: {response}")

        # 调用分发器处理响应
        # 分发器会自动将响应路由到对应的处理器
        self.dispatcher.dispatch(response)

    def run(self) -> None:
        """
        启动主事件循环
        
        说明:
            - 进入循环状态，保持系统运行
            - ROS2的回调函数（_on_asr_data, _on_thor_response）会被后台线程调用
            - 用户可以按 Ctrl+C 停止系统
            - 系统会优雅关闭（清理资源）
        """
        self.running = True
        logger.info("=" * 60)
        logger.info("🚀 G1 机器人控制器 - 运行中")
        logger.info("按 Ctrl+C 停止系统")
        logger.info("=" * 60)

        try:
            while self.running:
                # 主循环 - 保持系统运行
                # ROS2的回调函数会在后台线程处理消息
                time.sleep(0.1)

        except KeyboardInterrupt:
            logger.info("\n⏹️ 接收到键盘中断信号(Ctrl+C)")
            self.stop()

    def stop(self) -> None:
        """
        停止机器人控制器并清理资源
        
        清理步骤:
            1. 停止监听ASR语音输入
            2. 停止监听Thor响应
            3. 关闭TTS扬声器
            4. 输出停止日志
        """
        self.running = False
        logger.info("=" * 60)
        logger.info("🛑 正在停止 G1 机器人控制器")
        logger.info("=" * 60)

        # 优雅关闭所有监听器
        if self.asr_listener:
            self.asr_listener.stop()
        if self.thor_listener:
            self.thor_listener.stop()

        # 关闭TTS扬声器（如可用）
        if self.speaker:
            try:
                self.speaker.close()
            except Exception as e:
                logger.warning(f"Failed to close speaker: {e}")

        # 关闭/清理Thor发送器（如可用）
        if self.thor_sender:
            try:
                # 如果发送器实现了关闭方法，调用它；否则解除引用
                if hasattr(self.thor_sender, "close"):
                    self.thor_sender.close()
                self.thor_sender = None
            except Exception as e:
                logger.warning(f"Failed to cleanup thor_sender: {e}")

        logger.info("✅ G1 机器人控制器已停止")


def main():
    """
    Main entry point.
    """
    parser = argparse.ArgumentParser(
        description="G1 Robot Controller",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m g1_robot_controller eth0
  python -m g1_robot_controller wlan0
        """,
    )

    parser.add_argument(
        "network_interface",
        help="Network interface (e.g., eth0, wlan0)",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # Set debug level if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")

    # Create and run controller
    controller = G1RobotController(args.network_interface)

    if not controller.initialize():
        logger.error("Failed to initialize controller")
        sys.exit(1)

    controller.run()


if __name__ == "__main__":
    main()
