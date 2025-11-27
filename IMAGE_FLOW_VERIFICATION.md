# 图像传输流程验证文档

## 🔍 完整图像处理流程

### G1端（发送方）

#### 1. 摄像头捕获
```python
# camera_reader.py
cap = cv2.VideoCapture(4)  # 打开 /dev/video4
ret, frame = cap.read()     # frame 是 numpy array, shape=(480, 640, 3), dtype=uint8
```
**输出**: OpenCV图像数组 (BGR格式)

#### 2. 保存为JPEG文件
```python
# camera_reader.py
save_path = "/tmp/g1_captured_xxx.jpg"
cv2.imwrite(save_path, frame)
```
**输出**: JPEG文件

#### 3. 读取并Base64编码
```python
# thor_sender.py -> _encode_image()
with open(image_path, "rb") as f:
    image_data = f.read()                          # 二进制数据
    image_b64 = base64.b64encode(image_data).decode("utf-8")  # Base64字符串
```
**输出**: Base64编码的字符串

#### 4. 打包JSON消息
```python
# thor_sender.py -> send_asr_with_image()
message = {
    "text": "你好",
    "asr_text": "你好",
    "image_base64": image_b64,  # Base64字符串
    "timestamp": 1732608123.456,
    "request_id": "550e8400-..."
}
json_str = json.dumps(message)
```

#### 5. ROS2发送
```python
ros_msg = String_()
ros_msg.data = json_str  # JSON字符串
publisher.Write(ros_msg)
```

---

### Thor端（接收方）

#### 6. ROS2接收
```python
# thor_vlm_server.py -> _on_request()
raw_data = msg.data  # 获取JSON字符串
data = json.loads(raw_data)  # 解析为字典
```

#### 7. 提取Base64数据
```python
image_b64 = data.get("image_base64", "")
```

#### 8. Base64解码
```python
img_data = base64.b64decode(image_b64)  # 解码为二进制数据
```

#### 9. 转换为numpy数组
```python
nparr = np.frombuffer(img_data, np.uint8)  # 创建numpy数组
image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)  # 解码JPEG -> OpenCV图像
```
**输出**: OpenCV图像数组 (BGR格式), shape=(480, 640, 3)

#### 10. 转换为PIL Image
```python
image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)  # BGR -> RGB
pil_image = Image.fromarray(image_rgb)
```
**输出**: PIL Image对象 (RGB格式)

#### 11. 保存为临时文件（Qwen需要）
```python
temp_image_path = "/tmp/thor_temp_image.jpg"
pil_image.save(temp_image_path)
img_path = f"file://{temp_image_path}"
```
**输出**: 文件路径字符串 `file:///tmp/thor_temp_image.jpg`

#### 12. Qwen模型推理
```python
messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "image",
                "image": img_path,  # file:///tmp/thor_temp_image.jpg
                "resized_height": 280,
                "resized_width": 420
            },
            {"type": "text", "text": query}
        ]
    }
]

# Qwen处理
image_inputs, video_inputs = process_vision_info(messages)
inputs = processor(text=[text], images=image_inputs, ...)
outputs = model.generate(**inputs)
```

---

## ✅ 关键验证点

### 1. 格式兼容性
- **G1发送**: JPEG图像 -> Base64字符串 -> JSON
- **Thor接收**: JSON -> Base64字符串 -> JPEG二进制 -> OpenCV数组 -> PIL Image -> 临时文件
- **Qwen读取**: file:// 路径 -> PIL Image

✅ **完全兼容**

### 2. 图像尺寸
- G1拍摄: 640x480 (config.CAMERA_WIDTH x CAMERA_HEIGHT)
- Thor接收: 640x480 (解码后保持不变)
- Qwen处理: 调整为 420x280 (IMAGE_WIDTH x IMAGE_HEIGHT)

✅ **尺寸正确处理**

### 3. 颜色空间
- G1拍摄: BGR (OpenCV默认)
- 保存JPEG: BGR -> JPEG (自动处理)
- Thor解码: JPEG -> BGR (OpenCV解码)
- 转PIL: BGR -> RGB (cv2.cvtColor转换)
- Qwen: RGB (PIL Image)

✅ **颜色空间正确转换**

### 4. 数据完整性
- Base64编码/解码是**无损**的
- JPEG保存/读取可能有**轻微压缩损失**（质量默认95%）
- 对VLM推理影响**可忽略**

✅ **数据完整性保证**

---

## 🧪 测试方法

### 快速验证（部署后）

#### 方法1: 检查日志

**G1端日志**:
```
📷 Image captured: /tmp/g1_captured_xxx.jpg (640x480)
Image encoded: 123456 bytes  # Base64后的大小
📤 Sent to Thor: '你好' with image
```

**Thor端日志**:
```
📨 收到请求 (ID: xxx...)
📷 图像解码成功: (480, 640, 3)  # 应该看到这个
🧠 开始VLM推理...
```

如果看到 `📷 图像解码成功: (480, 640, 3)`，说明图像传输成功！

#### 方法2: 检查临时文件

在Thor服务器上:
```bash
# 运行Thor服务器，让G1发送一次请求
# 然后检查临时文件
ls -lh /tmp/thor_temp_image.jpg

# 查看图像（如果Thor有GUI）
eog /tmp/thor_temp_image.jpg
# 或
feh /tmp/thor_temp_image.jpg
```

如果能看到图像，说明整个流程正常！

#### 方法3: 添加调试保存

在 `thor_vlm_server.py` 中临时添加：
```python
# 在 _on_request() 中，解码图像后
if image is not None:
    debug_path = f"/tmp/debug_received_{request_id[:8]}.jpg"
    cv2.imwrite(debug_path, image)
    logger.info(f"🔍 调试: 保存接收的图像到 {debug_path}")
```

然后检查 `/tmp/debug_received_*.jpg` 文件。

---

## ⚠️ 可能的问题和解决方案

### 问题1: Thor收到空图像
**症状**: 
```
⚠️ 图像解码失败: ...
```

**原因**: Base64编码/解码问题

**解决**:
检查G1端是否正确编码：
```python
# thor_sender.py
logger.info(f"Image encoded: {len(image_b64)} bytes")
```

### 问题2: 图像尺寸不对
**症状**: 
```
📷 图像解码成功: (0, 0, 3)  # 错误的尺寸
```

**原因**: JPEG解码失败

**解决**:
检查JPEG文件是否有效：
```bash
file /tmp/g1_captured_xxx.jpg
# 应该输出: JPEG image data, ...
```

### 问题3: Qwen无法读取图像
**症状**: 
```
错误: cannot identify image file ...
```

**原因**: 临时文件路径或格式问题

**解决**:
```python
# 确保保存成功
pil_image.save(temp_image_path)
assert os.path.exists(temp_image_path), "临时文件未创建"
logger.info(f"临时文件大小: {os.path.getsize(temp_image_path)} bytes")
```

---

## 📊 性能数据参考

### 典型图像大小
- 原始图像 (640x480 BGR): ~900 KB
- JPEG压缩后: ~50-150 KB
- Base64编码后: ~70-200 KB
- JSON消息总大小: ~70-200 KB

### 传输时间估计
- 局域网 (100 Mbps): ~10-20 ms
- WiFi (50 Mbps): ~20-50 ms
- 编码/解码时间: ~5-10 ms

**总图像传输延迟**: ~50-100 ms

---

## 🎯 结论

**✅ 图像传输流程完全可行！**

你的代码示例中使用：
```python
img_path = "/home/bryce/Pictures/person.jpg"
img_path = f"file://{img_path}"
```

而我的实现是：
```python
# 接收Base64 -> 解码 -> 保存临时文件 -> 使用file://路径
temp_image_path = "/tmp/thor_temp_image.jpg"
pil_image.save(temp_image_path)
img_path = f"file://{temp_image_path}"
```

**两者本质相同**，都是给Qwen提供 `file://` 路径。

唯一区别：
- 你的示例: 静态图像文件
- 我的实现: 动态接收的图像（每次请求都不同）

**Thor能完全正确解析G1发送的图像！** 🎉

---

## 📝 部署检查清单

部署时验证图像传输：

- [ ] G1能拍照（检查日志: `📷 Image captured`）
- [ ] G1能编码（检查日志: `Image encoded: xxx bytes`）
- [ ] G1能发送（检查日志: `📤 Sent to Thor`）
- [ ] Thor能接收（检查日志: `📨 收到请求`）
- [ ] Thor能解码（检查日志: `📷 图像解码成功`）
- [ ] Thor能保存临时文件（检查 `/tmp/thor_temp_image.jpg` 存在）
- [ ] Qwen能读取图像（检查日志: `⚡ 执行模型推理...`）
- [ ] 完整流程正常（检查日志: `✅ 响应已发送`）

全部通过即表示图像传输完全正常！
