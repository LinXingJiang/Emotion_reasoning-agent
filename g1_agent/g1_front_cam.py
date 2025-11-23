import pyrealsense2 as rs
import numpy as np
import cv2

pipeline = rs.pipeline()
config = rs.config()

config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
pipeline.start(config)

frames = pipeline.wait_for_frames()
color_frame = frames.get_color_frame()

color = np.asanyarray(color_frame.get_data())
cv2.imwrite("color_test.jpg", color)

print("Saved color_test.jpg")