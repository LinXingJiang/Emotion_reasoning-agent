# =========================================================
#   photo_capture.py —— OpenCV 摄像头（带自动释放，最稳定）
# =========================================================

import cv2
import os

VIDEO_DEVICE = 4   # 你的设备是 /dev/video4

def capture_image(save_name="g1_last_frame.jpg"):
    """
    每次拍照：
    1. 打开摄像头
    2. 读取一帧
    3. 保存
    4. 关闭摄像头（关键！）
    """
    print(f"[CAMERA] Opening /dev/video{VIDEO_DEVICE}...")

    cap = cv2.VideoCapture(VIDEO_DEVICE)

    if not cap.isOpened():
        print(f"[CAMERA ERROR] Cannot open /dev/video{VIDEO_DEVICE}")
        return None

    # 设置分辨率（可选）
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    ret, frame = cap.read()

    # ⭐ 关键：读取完必须立即释放
    cap.release()

    if not ret:
        print("[CAMERA ERROR] Failed to capture frame.")
        return None

    save_path = os.path.join(os.getcwd(), save_name)
    cv2.imwrite(save_path, frame)

    print(f"[IMAGE] Saved: {save_path}")
    return save_path