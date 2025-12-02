"""
camera_reader.py - 摄像头读取器（RealSense D435i）

功能说明:
    这个模块负责从G1机器人头顶的Intel RealSense D435i深度摄像头捕获图像。
    使用pyrealsense2库进行摄像头操作，支持彩色图和深度图。

主要特性:
    1. 图像捕获 - 支持彩色图和深度图
    2. 资源管理 - 每次捕获后自动释放摄像头资源，避免资源冲突
    3. 硬件识别 - 通过设备序列号锁定指定D435i摄像头
    4. 错误处理 - 完善的异常处理和日志记录

数据流:
    启动pipeline → 配置流 → 等待帧
        ↓
    获取彩色图/深度图 → 保存 → 停止pipeline

资源管理说明:
    - 为避免资源竞争，每次capture()都会启动和停止pipeline
    - 适合周期性拍照的应用场景
    - 不适合持续视频流处理

使用例子:
    reader = CameraReader()
    image, path = reader.capture()  # 拍一张照片（仅彩色）
    reader.capture_and_save("photo.jpg")  # 拍照并保存
"""

import os
import logging
import time
from typing import Optional

import cv2
import numpy as np
import pyrealsense2 as rs

from ..utils import config

logger = logging.getLogger(__name__)


class CameraReader:
    """
    摄像头读取器 - 从G1机器人头顶RealSense D435i捕获图像
    
    主要功能:
        1. 连接到指定的RealSense D435i设备（通过序列号）
        2. 配置彩色流和深度流
        3. 读取单帧彩色图像
        4. 自动保存图像到文件
        5. 停止pipeline并释放资源
    
    资源管理策略:
        - 采用"启动-使用-停止"模式
        - 每次capture()调用都会启动和停止pipeline
        - 这样做可以避免资源竞争（特别是多个进程访问摄像头）
        - 缺点是速度较慢，但对于间断拍照来说足够了
    
    摄像头配置:
        device_sn: RealSense设备序列号（默认"233722074381"）
        width: 图像宽度（像素）
        height: 图像高度（像素）
        fps: 帧率（RealSense建议15fps以确保稳定性）
    
    使用例子:
        reader = CameraReader()
        image, path = reader.capture()  # 获取图像numpy数组和保存路径
        
        reader.capture_and_save("photo.jpg")  # 直接拍照并保存
    """

    def __init__(
        self,
        device_sn: str = None,
        width: int = None,
        height: int = None,
        fps: int = None
    ):
        """
        初始化RealSense摄像头读取器
        
        参数:
            device_sn: RealSense设备序列号
                      如果为None，使用默认值"233722074381"（G1头顶D435i）
            width: 图像宽度（像素）
                  如果为None，使用config.CAMERA_WIDTH配置（默认640）
            height: 图像高度（像素）
                   如果为None，使用config.CAMERA_HEIGHT配置（默认480）
            fps: 帧率（每秒帧数）
                如果为None，使用15fps（RealSense推荐值）
        
        例子:
            # 使用默认配置
            reader = CameraReader()
            
            # 自定义配置
            reader = CameraReader(device_sn="233722074381", width=640, height=480, fps=15)
        """
        self.device_sn = device_sn or "233722074381"  # G1头顶D435i序列号
        self.width = width or config.CAMERA_WIDTH
        self.height = height or config.CAMERA_HEIGHT
        self.fps = fps or 15  # RealSense建议使用15fps以确保所有设备兼容

    def capture(self, save_path: Optional[str] = None) -> Optional[tuple]:
        """
        从RealSense D435i捕获单帧彩色图像
        
        工作流程:
            1. 创建RealSense pipeline和config
            2. 配置设备序列号和流参数
            3. 启动pipeline
            4. 等待并获取帧（最多重试10次）
            5. 提取彩色图像
            6. 保存图像到文件（如果提供路径）
            7. 停止pipeline（finally块确保总是执行）
        
        参数:
            save_path: 图像保存路径
                      如果为None，使用默认路径: {SAVE_DIR}/{IMAGE_FILENAME}
                      例如: "./images/photo.jpg"
        
        返回:
            成功: 返回元组 (image_array, save_path)
                 image_array: numpy数组格式的BGR彩色图像
                 save_path: 图像保存的文件路径
            失败: 返回None（会记录错误日志）
        
        错误情况:
            - pipeline启动失败: 记录错误并返回None
            - 获取帧失败（重试10次后）: 记录错误并返回None
            - 保存图像失败: 记录错误并返回None
        
        例子:
            reader = CameraReader()
            result = reader.capture()
            if result:
                image, path = result
                print(f"图像已保存到: {path}")
            else:
                print("拍照失败")
        
        重要说明:
            - finally块确保pipeline总是被正确停止
            - 这防止了摄像头被长期占用导致的冲突问题
        """
        logger.debug(f"Starting RealSense pipeline (SN: {self.device_sn})...")

        pipeline = rs.pipeline()
        rs_config = rs.config()

        try:
            # 配置设备和流
            rs_config.enable_device(self.device_sn)
            rs_config.enable_stream(
                rs.stream.color, 
                self.width, 
                self.height, 
                rs.format.bgr8, 
                self.fps
            )
            rs_config.enable_stream(
                rs.stream.depth, 
                self.width, 
                self.height, 
                rs.format.z16, 
                self.fps
            )

            # 启动pipeline
            profile = pipeline.start(rs_config)
            logger.debug("RealSense pipeline started")

            # 等待设备稳定
            time.sleep(0.5)

            # 尝试获取帧（最多重试10次）
            frame = None
            for attempt in range(10):
                try:
                    frames = pipeline.wait_for_frames(timeout_ms=5000)
                    color_frame = frames.get_color_frame()

                    if color_frame:
                        # 转换为numpy数组
                        frame = np.asanyarray(color_frame.get_data())
                        logger.debug(f"Got frame on attempt {attempt + 1}")
                        break
                    else:
                        logger.debug(f"No color frame on attempt {attempt + 1}, retrying...")
                except Exception as e:
                    logger.debug(f"Frame acquisition error on attempt {attempt + 1}: {e}")

            if frame is None:
                logger.error("Failed to capture frame from RealSense after 10 attempts")
                return None

            # Determine save path
            if save_path is None:
                save_path = os.path.join(config.SAVE_DIR, config.IMAGE_FILENAME)

            # Create directory if needed
            os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)

            # Save image
            success = cv2.imwrite(save_path, frame)

            if success:
                logger.info(f"📷 Image captured: {save_path} ({self.width}x{self.height})")
                return (frame, save_path)
            else:
                logger.error(f"Failed to save image to {save_path}")
                return None

        except Exception as e:
            logger.error(f"RealSense camera capture error: {e}")
            return None

        finally:
            # CRITICAL: Always stop the pipeline
            try:
                pipeline.stop()
                logger.debug("RealSense pipeline stopped")
            except Exception as e:
                logger.debug(f"Error stopping pipeline: {e}")

    def capture_and_save(self, filename: str = None) -> Optional[str]:
        """
        拍照并保存到文件
        
        功能:
            - 这是capture()方法的简化版本
            - 自动确定保存路径，只需提供文件名
            - 返回保存的文件路径
        
        参数:
            filename: 自定义文件名（不包括目录路径）
                     例如: "photo.jpg"
                     如果为None，使用config.IMAGE_FILENAME（默认值）
        
        返回:
            成功: 返回图像保存的文件路径（字符串）
            失败: 返回None
        
        例子:
            reader = CameraReader()
            path = reader.capture_and_save("my_photo.jpg")
            if path:
                print(f"保存成功: {path}")
        
        说明:
            这个方法调用capture()，但只返回文件路径，不返回图像数组。
            如果需要图像数组用于进一步处理，请直接使用capture()。
        """
        if filename:
            save_path = os.path.join(config.SAVE_DIR, filename)
        else:
            save_path = None

        result = self.capture(save_path)
        return result[1] if result else None


# Global camera instance
_camera: Optional[CameraReader] = None


def get_camera() -> CameraReader:
    """
    获取或创建全局摄像头实例
    
    说明:
        - 使用单例模式确保全局只有一个CameraReader实例
        - 第一次调用时创建实例，后续调用返回同一实例
        - 这样可以避免重复初始化摄像头配置
    
    返回:
        CameraReader实例
    
    例子:
        camera = get_camera()
        image, path = camera.capture()
    """
    global _camera
    if _camera is None:
        _camera = CameraReader()
    return _camera


def capture_image(save_path: Optional[str] = None) -> Optional[tuple]:
    """
    便利函数 - 拍照并返回图像和路径
    
    说明:
        - 这是对get_camera().capture()的简化包装
        - 不需要显式获取CameraReader实例
    
    参数:
        save_path: 可选的保存路径
        
    返回:
        成功: 元组 (image_array, save_path)
        失败: None
    
    例子:
        result = capture_image()
        if result:
            image, path = result
    """
    return get_camera().capture(save_path)


def capture_and_save(filename: str = None) -> Optional[str]:
    """
    便利函数 - 拍照并保存，返回文件路径
    
    说明:
        - 简化版本的capture_and_save()
        - 只需提供文件名，自动确定完整路径
    
    参数:
        filename: 可选的自定义文件名
        
    返回:
        保存的文件路径，或None（失败）
    
    例子:
        path = capture_and_save("photo.jpg")
    """
    return get_camera().capture_and_save(filename)
