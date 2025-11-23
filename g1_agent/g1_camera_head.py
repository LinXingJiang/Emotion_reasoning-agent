import pyrealsense2 as rs
import numpy as np
import cv2
import time

DEVICE_SN = "233722074381"   # 头顶 D435i

pipeline = rs.pipeline()
config = rs.config()

# 只启动 D435i，并用最低规格启动（所有 D435i 都支持）
config.enable_device(DEVICE_SN)
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 15)
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 15)

print("Starting pipeline...")
profile = pipeline.start(config)

time.sleep(1)  # 给设备一点时间启动

print("Waiting for frames...")
for i in range(10):
    try:
        frames = pipeline.wait_for_frames(5000)
        color = frames.get_color_frame()
        depth = frames.get_depth_frame()

        if color and depth:
            print(f"Got frame {i} !")
            color_np = np.asanyarray(color.get_data())
            depth_np = np.asanyarray(depth.get_data())

            cv2.imwrite("head_color_test.jpg", color_np)
            cv2.imwrite("head_depth_test.png", depth_np)
            print("Saved test images!")
            break
        else:
            print("No data, retrying...")

    except Exception as e:
        print("Error:", e)

pipeline.stop()
print("Pipeline stopped.")