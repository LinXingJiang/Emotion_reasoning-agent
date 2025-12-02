"""
config.py - 配置模块

功能说明:
    这个模块集中管理G1机器人控制系统的所有配置参数。
    包括网络、摄像头、音频、TTS、ASR以及Thor通信等配置。

配置方式:
    1. 优先级：环境变量 > 默认值
    2. 所有配置都可以通过环境变量覆盖
    3. 默认值在代码中定义，适合大多数场景
    4. 对于特殊配置，设置相应的环境变量即可

配置分类:
    - NETWORK: 网络和ROS2频道配置
    - CAMERA: RealSense D435i摄像头参数（设备序列号、分辨率等）
    - AUDIO: TTS和ASR的音频配置
    - THOR: Jetson Thor服务器通信配置
    - SYSTEM: 系统级配置（调试、日志级别等）

环境变量参考:
    G1_NET_IF: 网络接口名称（默认 eth0）
    G1_REALSENSE_SN: RealSense设备序列号（默认 233722074381）
    G1_CAMERA_WIDTH: 图像宽度（默认 640）
    G1_CAMERA_HEIGHT: 图像高度（默认 480）
    G1_CAMERA_FPS: 摄像头帧率（默认 15，RealSense推荐值）
    G1_SPEAKER: TTS语言（默认 1=英文，0=中文）
    G1_TTS_TIMEOUT: TTS超时时间（默认 10.0秒）
    G1_ASR_TOPIC: ASR话题名称（默认 "rt/audio_msg"）
    G1_THOR_HOST: Thor服务器地址（默认 192.168.1.100）
    G1_THOR_PORT: Thor服务器端口（默认 5000）
    G1_THOR_SEND_TOPIC: Thor请求话题（默认 "rt/thor_request"）
    G1_THOR_RECV_TOPIC: Thor响应话题（默认 "rt/thor_response"）
    G1_DEBUG: 调试模式（默认 False）
    G1_LOG_LEVEL: 日志级别（默认 INFO）
    G1_SAVE_DIR: 图像保存目录（默认 当前工作目录）

使用例子:
    # Python代码中使用配置
    from g1_robot_controller.utils import config
    
    print(config.CAMERA_DEVICE)  # 输出: 4
    print(config.NETWORK_INTERFACE)  # 输出: eth0
    
    # 命令行设置环境变量
    export G1_CAMERA_DEVICE=6
    export G1_NETWORK_INTERFACE=wlan0
    python main.py
"""

import os
import sys

# ============================================================
# 网络和ROS2频道配置
# ============================================================
# 网络接口名称（例如 "eth0", "wlan0"）
# 用于ROS2 DDS通信，在运行时可以通过环境变量或命令行参数设置
NETWORK_INTERFACE = os.getenv("G1_NET_IF", "eth0")

# ============================================================
# 摄像头配置（Intel RealSense D435i）
# ============================================================
# RealSense设备序列号（G1头顶D435i）
REALSENSE_DEVICE_SN = os.getenv("G1_REALSENSE_SN", "233722074381")

# 图像分辨率：宽度（像素）
CAMERA_WIDTH = int(os.getenv("G1_CAMERA_WIDTH", "640"))

# 图像分辨率：高度（像素）
CAMERA_HEIGHT = int(os.getenv("G1_CAMERA_HEIGHT", "480"))

# 摄像头帧率（每秒帧数）
# RealSense D435i推荐使用15fps以确保所有设备兼容
CAMERA_FPS = int(os.getenv("G1_CAMERA_FPS", "15"))

# 保留旧的CAMERA_DEVICE配置用于兼容性（已弃用）
CAMERA_DEVICE = int(os.getenv("G1_CAMERA_DEVICE", "4"))

# ============================================================
# 音频和文本转语音（TTS）配置
# ============================================================
# 默认扬声器ID
# 0 = 中文语音
# 1 = 英文语音
DEFAULT_SPEAKER = int(os.getenv("G1_SPEAKER", "1"))

# TTS（文本转语音）操作的超时时间（秒）
# 防止语音合成过程中出现卡顿
TTS_TIMEOUT = float(os.getenv("G1_TTS_TIMEOUT", "10.0"))

# ============================================================
# 语音识别（ASR）配置
# ============================================================
# ASR（自动语音识别）话题名称
# 机器人音频系统通过这个话题发布识别结果
ASR_TOPIC = os.getenv("G1_ASR_TOPIC", "rt/audio_msg")

# ============================================================
# Thor（Jetson推理服务器）通信配置
# ============================================================
# Thor服务器的网络地址（IP地址）
# 这是Jetson设备运行的推理服务器地址
THOR_HOST = os.getenv("G1_THOR_HOST", "192.168.1.100")

# Thor服务器的网络端口
THOR_PORT = int(os.getenv("G1_THOR_PORT", "5000"))

# 发送给Thor的请求话题
# 本地G1通过这个话题发送ASR文本和图像给Thor
THOR_SEND_TOPIC = os.getenv("G1_THOR_SEND_TOPIC", "rt/thor_request")

# 接收Thor响应的话题
# Thor通过这个话题返回推理结果（动作、语音等）
THOR_RECV_TOPIC = os.getenv("G1_THOR_RECV_TOPIC", "rt/thor_response")

# ============================================================
# 系统级配置
# ============================================================
# 调试模式开关
# True = 启用详细的调试输出和额外的日志信息
# False = 仅输出关键信息
DEBUG = os.getenv("G1_DEBUG", "False").lower() == "true"

# 日志级别
# 支持的级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
# 默认为INFO级别
LOG_LEVEL = os.getenv("G1_LOG_LEVEL", "INFO")

# 图像保存目录
# 拍照和其他图像操作的输出目录
SAVE_DIR = os.getenv("G1_SAVE_DIR", os.getcwd())

# 图像文件名
# 保存最后一帧的默认文件名
IMAGE_FILENAME = "g1_last_frame.jpg"
