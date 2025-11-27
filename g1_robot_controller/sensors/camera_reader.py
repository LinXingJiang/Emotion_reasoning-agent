"""
camera_reader.py - 摄像头读取器

功能说明:
    这个模块负责从G1机器人的前置摄像头捕获图像。
    使用OpenCV库进行摄像头操作，支持自动保存图像。

主要特性:
    1. 图像捕获 - 支持单帧捕获
    2. 资源管理 - 每次捕获后自动释放摄像头资源，避免资源冲突
    3. 配置灵活 - 支持自定义摄像头设备、分辨率等
    4. 错误处理 - 完善的异常处理和日志记录

数据流:
    打开摄像头 → 设置分辨率 → 读取一帧
        ↓
    图像处理/保存 → 释放摄像头资源

资源管理说明:
    - 为避免资源竞争，每次capture()都会打开和关闭摄像头
    - 适合周期性拍照的应用场景
    - 不适合持续视频流处理

使用例子:
    reader = CameraReader()
    image, path = reader.capture()  # 拍一张照片
    reader.capture_and_save("photo.jpg")  # 拍照并保存
"""

import os
import logging
from typing import Optional

import cv2

from ..utils import config

logger = logging.getLogger(__name__)


class CameraReader:
    """
    摄像头读取器 - 从G1机器人前置摄像头捕获图像
    
    主要功能:
        1. 连接到指定的摄像头设备（通过OpenCV）
        2. 设置摄像头分辨率
        3. 读取单帧图像
        4. 自动保存图像到文件
        5. 关闭摄像头并释放资源
    
    资源管理策略:
        - 采用"打开-使用-关闭"模式
        - 每次capture()调用都会打开和关闭摄像头
        - 这样做可以避免资源竞争（特别是多个进程访问摄像头）
        - 缺点是速度较慢，但对于间断拍照来说足够了
    
    摄像头配置:
        device: 摄像头设备号（例如4对应/dev/video4）
        width: 图像宽度（像素）
        height: 图像高度（像素）
    
    使用例子:
        reader = CameraReader()
        image, path = reader.capture()  # 获取图像numpy数组和保存路径
        
        reader.capture_and_save("photo.jpg")  # 直接拍照并保存
    """

    def __init__(self, device: int = None, width: int = None, height: int = None):
        """
        初始化摄像头读取器
        
        参数:
            device: 摄像头设备号（例如4表示/dev/video4）
                   如果为None，使用config.CAMERA_DEVICE配置
            width: 图像宽度（像素）
                  如果为None，使用config.CAMERA_WIDTH配置（默认640）
            height: 图像高度（像素）
                   如果为None，使用config.CAMERA_HEIGHT配置（默认480）
        
        例子:
            # 使用默认配置
            reader = CameraReader()
            
            # 自定义配置
            reader = CameraReader(device=4, width=1280, height=720)
        """
        self.device = device or config.CAMERA_DEVICE
        self.width = width or config.CAMERA_WIDTH
        self.height = height or config.CAMERA_HEIGHT

    def capture(self, save_path: Optional[str] = None) -> Optional[tuple]:
        """
        从摄像头捕获单帧图像
        
        工作流程:
            1. 打开指定的摄像头设备
            2. 设置摄像头分辨率（width x height）
            3. 读取一帧图像
            4. 保存图像到文件（如果提供路径）
            5. 关闭摄像头（finally块确保总是关闭）
        
        参数:
            save_path: 图像保存路径
                      如果为None，使用默认路径: {SAVE_DIR}/{IMAGE_FILENAME}
                      例如: "./images/photo.jpg"
        
        返回:
            成功: 返回元组 (image_array, save_path)
                 image_array: numpy数组格式的图像（可用于进一步处理）
                 save_path: 图像保存的文件路径
            失败: 返回None（会记录错误日志）
        
        错误情况:
            - 摄像头无法打开: 记录错误并返回None
            - 读取帧失败: 记录错误并返回None
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
            - finally块确保摄像头资源总是被正确释放
            - 这防止了摄像头被长期占用导致的冲突问题
        """
        logger.debug(f"Opening camera /dev/video{self.device}...")

        cap = cv2.VideoCapture(self.device)

        if not cap.isOpened():
            logger.error(f"Cannot open camera /dev/video{self.device}")
            return None

        try:
            # Set resolution
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

            # Read frame
            ret, frame = cap.read()

            if not ret:
                logger.error("Failed to capture frame from camera")
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
            logger.error(f"Camera capture error: {e}")
            return None

        finally:
            # CRITICAL: Always release the camera resource
            cap.release()
            logger.debug(f"Camera /dev/video{self.device} released")

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
