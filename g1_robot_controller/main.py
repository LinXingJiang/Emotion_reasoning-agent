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
from .comm.thor_sender import get_thor_sender       # Thor HTTP发送器
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
        1. 初始化所有子系统（ASR、TTS、摄像头、Thor HTTP客户端、分发器）
        2. 管理系统事件循环
        3. 处理ASR语音输入回调
        4. 同步调用Thor推理并分发结果
        5. 提供优雅的系统关闭
    
    数据流向（HTTP同步模式）:
        ASR语音输入 → _on_asr_data() → Thor HTTP发送器
                                          ↓ (POST /infer)
                                    Jetson Thor处理
                                          ↓ (JSON响应)
                                      分发器处理
        ├→ 扬声器(TTS语音输出)
        ├→ 动作执行器(手势、移动、系统命令)
        └→ 自定义处理器(用户扩展)
    """

    def __init__(self, network_interface: str):
        """
        初始化机器人控制器
        
        参数:
            network_interface: 网络接口名称 (例如: 'eth0', 'wlan0')
                              用于ROS2 DDS通信（仅ASR监听）
        """
        self.network_interface = network_interface
        self.running = False
        
        # 系统组件（延迟初始化）
        self.asr_listener: Optional[ASRListener] = None           # 语音识别监听器
        self.thor_sender = None                                   # Thor HTTP发送器
        self.dispatcher = None                                    # 响应分发器
        self.speaker = None                                       # 文本转语音

    def initialize(self) -> bool:
        """
        初始化所有系统组件
        
        初始化顺序:
            1. ROS2 DDS通信通道 - 仅用于ASR监听
            2. TTS扬声器 - 负责机器人发出语音
            3. Thor HTTP发送器 - 将ASR和图像POST到Jetson Thor
            4. 响应分发器 - 路由Thor返回的推理结果
            5. ASR监听器 - 监听机器人麦克风的语音输入
        
        返回:
            True: 初始化成功
            False: 初始化失败（检查日志了解详情）
        """
        try:
            logger.info("=" * 60)
            logger.info("🤖 G1 机器人控制器 - 正在初始化")
            logger.info("=" * 60)

            # 第1步：初始化ROS2 DDS通信 - 仅用于ASR监听
            logger.info(f"📡 初始化ROS2 DDS，网络接口: {self.network_interface}")
            ChannelFactoryInitialize(0, self.network_interface)

            # 第2步：初始化TTS扬声器
            logger.info("🔊 初始化文本转语音(TTS)...")
            self.speaker = get_speaker()

            # 第3步：初始化Thor HTTP发送器
            logger.info("📤 初始化Thor HTTP发送器...")
            self.thor_sender = get_thor_sender()

            # 第4步：初始化响应分发器
            logger.info("⚙️ 初始化响应分发器...")
            self.dispatcher = get_dispatcher()

            # 第5步：初始化ASR语音识别监听器
            logger.info("🎤 初始化语音识别(ASR)监听器...")
            self.asr_listener = ASRListener(self._on_asr_data)
            self.asr_listener.start()

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
        
        工作流程（HTTP同步模式）:
            1. 接收ASR数据 (文本、信心度、角度)
            2. 调用Thor HTTP发送器发送请求
            3. 同步等待Thor返回推理结果
            4. 直接调用分发器处理结果
        
        参数:
            asr_data: 字典，包含:
                {
                    "text": "用户说的内容",
                    "confidence": 0.95,
                    "angle": 45.0
                }
        """
        logger.info(f"[ASR回调] 接收到: {asr_data}")

        # 提取用户说的文本
        text = asr_data.get("text", "")
        if text:
            logger.info(f"📤 发送给Thor: '{text}' (附带图像)")
            
            # 同步调用Thor发送器（自动拍照并发送）
            response = self.thor_sender.send_asr_with_image(text)
            
            # 如果收到响应，立即分发处理
            if response:
                logger.info(f"[Thor响应] 接收到: {response}")
                self.dispatcher.dispatch(response)
            else:
                logger.warning("Thor响应失败或超时")

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

        # 关闭TTS扬声器（如可用）
        if self.speaker:
            try:
                self.speaker.close()
            except Exception as e:
                logger.warning(f"Failed to close speaker: {e}")

        # 关闭Thor HTTP发送器
        if self.thor_sender:
            try:
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
