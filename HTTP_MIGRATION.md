# HTTP通信迁移完成总结

## ✅ 迁移完成

已将整个系统从 **ROS2 DDS通信** 迁移到 **HTTP/REST API通信**。

---

## 📊 架构变更

### 之前（ROS2 DDS）
```
G1 ──ROS2 Topic──> Thor (异步)
     rt/thor_request

Thor ──ROS2 Topic──> G1 (异步回调)
     rt/thor_response
```

### 现在（HTTP）
```
G1 ──HTTP POST──> http://THOR_IP:5000/infer (同步)
   └─ 等待响应 ─> JSON (立即返回)
```

---

## 🔧 修改的文件

### 1. **Thor VLM服务器** (`thor_vlm_server.py`)
- ❌ 删除：ROS2 `ChannelSubscriber`, `ChannelPublisher`
- ✅ 添加：Flask HTTP服务器
- ✅ 添加：POST `/infer` 端点
- ✅ 添加：GET `/health` 健康检查端点

**启动方式变更**：
```bash
# 之前
python thor_vlm_server.py eth0

# 现在
python thor_vlm_server.py [--host 0.0.0.0] [--port 5000] [--debug]
```

### 2. **G1 Thor发送器** (`g1_robot_controller/comm/thor_sender.py`)
- ❌ 删除：ROS2 `ChannelPublisher`
- ✅ 添加：`requests.Session()` HTTP客户端
- ✅ 修改：`send_asr_with_image()` 现在返回 `Dict` 而不是 `bool`
- ✅ 添加：同步HTTP POST请求到Thor

**使用方式变更**：
```python
# 之前
sender.send_asr_with_image(text)  # 异步发送，不等响应

# 现在
response = sender.send_asr_with_image(text)  # 同步请求，立即获取响应
if response:
    print(response["text"])
```

### 3. **G1 主控制器** (`g1_robot_controller/main.py`)
- ❌ 删除：`ThorListener` 导入和初始化
- ❌ 删除：`_on_thor_response()` 回调函数
- ✅ 修改：`_on_asr_data()` 现在同步调用Thor并立即分发响应

**数据流变更**：
```python
# 之前
def _on_asr_data(asr_data):
    self.thor_sender.send_asr_with_image(text)  # 发送后返回
    # 等待 _on_thor_response() 被异步调用

def _on_thor_response(response):
    self.dispatcher.dispatch(response)

# 现在
def _on_asr_data(asr_data):
    response = self.thor_sender.send_asr_with_image(text)  # 同步等待
    if response:
        self.dispatcher.dispatch(response)  # 立即分发
```

### 4. **配置文件** (`g1_robot_controller/utils/config.py`)
- ❌ 删除：`THOR_SEND_TOPIC`, `THOR_RECV_TOPIC`
- ✅ 添加：`THOR_HOST = "192.168.1.100"`
- ✅ 添加：`THOR_PORT = 5000`
- ✅ 添加：`THOR_URL = f"http://{THOR_HOST}:{THOR_PORT}"`
- ✅ 添加：`THOR_TIMEOUT = 30.0` (HTTP请求超时)

**环境变量**：
```bash
export G1_THOR_HOST=192.168.10.20
export G1_THOR_PORT=5000
export G1_THOR_URL=http://192.168.10.20:5000
export G1_THOR_TIMEOUT=30.0
```

### 5. **依赖管理** (`requirements.txt`)
- ✅ 添加G1端：`requests>=2.31.0` (HTTP客户端)
- ✅ 创建Thor端：`requirements_thor.txt`
  - `Flask>=3.0.0` (HTTP服务器)
  - `Werkzeug>=3.0.0`
  - `torch`, `transformers`, `qwen-vl-utils`, `Pillow`

### 6. **部署文档** (`部署指南.md`)
- ✅ 更新：系统架构图（HTTP通信）
- ✅ 更新：数据流向图
- ✅ 更新：Thor启动命令（无需网络接口参数）
- ✅ 添加：HTTP端点说明（POST /infer, GET /health）
- ✅ 添加：Thor URL配置说明

---

## 🚀 部署步骤

### Jetson Thor端

```bash
# 1. 安装依赖
pip install -r requirements_thor.txt

# 2. 启动HTTP服务器
python thor_vlm_server.py

# 或自定义端口
python thor_vlm_server.py --port 8000

# 3. 测试健康检查
curl http://localhost:5000/health
```

### G1机器人端

```bash
# 1. 安装依赖（包含requests）
pip install -r requirements.txt

# 2. 配置Thor URL
export G1_THOR_URL=http://192.168.10.20:5000

# 3. 启动控制器
python -m g1_robot_controller eth0
```

---

## 📡 HTTP API

### POST /infer

**请求**：
```json
{
  "text": "用户说的话",
  "image_base64": "iVBORw0KGgoAAAANS...",
  "request_id": "uuid",
  "timestamp": 1733184000.0
}
```

**响应**：
```json
{
  "status": "success",
  "text": "机器人回复",
  "action": "wave",
  "action_type": "gesture",
  "emotion": "happy",
  "confidence": 0.95,
  "request_id": "uuid",
  "analysis": {"age": 25, "gender": "male", "emotion": "happy"}
}
```

### GET /health

**响应**：
```json
{
  "status": "healthy",
  "model_loaded": true,
  "model_path": "/home/bryce/models/Qwen2.5-VL-3B-Instruct"
}
```

---

## ⚙️ 优势

1. **更简单的部署**：无需在G1和Thor间配置ROS2网络接口一致性
2. **更好的调试**：可使用curl/Postman直接测试Thor API
3. **更清晰的流程**：同步请求-响应模式，更易理解和维护
4. **更好的错误处理**：HTTP状态码 + timeout控制
5. **更灵活的扩展**：可轻松添加新的HTTP端点

---

## 📝 注意事项

1. **网络配置**：确保G1可以ping通Thor的IP地址
2. **防火墙**：Thor端口5000需要开放（如有防火墙）
3. **超时设置**：默认30秒，VLM推理较慢可适当增加
4. **ASR监听**：仍使用ROS2（G1内部通信），需要网络接口参数

---

## 🔄 回滚方案

如需回滚到ROS2版本：
```bash
cd g1_robot_controller/comm
mv thor_sender.py thor_sender_http.py
mv thor_sender_old.py thor_sender.py
```

然后恢复 `main.py` 中的 `ThorListener` 相关代码。

---

**迁移完成！系统现在使用标准HTTP/REST API通信。** 🎉
