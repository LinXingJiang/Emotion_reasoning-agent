"""
Thor VLM 推理服务器 - 基于 Qwen2.5-VL-3B-Instruct
功能: 接收G1发送的图像和文本，进行VLM推理，返回响应
模型: Qwen2.5-VL-3B-Instruct (人物分析、情感识别)
通信: HTTP/REST API (Flask)
"""

import json
import logging
import base64
import numpy as np
import cv2
import torch
import re
from PIL import Image
from flask import Flask, request, jsonify

from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info

# ============================================================
# 配置日志
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================
# 配置参数
# ============================================================
HOST = "0.0.0.0"
PORT = 5000

MODEL_PATH = "Qwen/Qwen2.5-VL-3B-Instruct"   # 在线模型路径（自动缓存）
IMAGE_HEIGHT = 280
IMAGE_WIDTH = 420
PIXELS = IMAGE_HEIGHT * IMAGE_WIDTH


# ============================================================
# 上下文管理器（支持多轮对话）
# ============================================================
class ContextManager:
    def __init__(self, max_turns: int = 10):
        self.max_turns = max_turns
        self.history = []
        logger.info(f"📚 上下文管理器初始化: 最大保留 {max_turns} 轮对话")

    def add_user(self, text: str):
        self.history.append({"role": "user", "content": text})
        self._trim()

    def add_assistant(self, text: str):
        self.history.append({"role": "assistant", "content": text})
        self._trim()

    def _trim(self):
        if len(self.history) > self.max_turns * 2:
            self.history = self.history[-self.max_turns * 2:]

    def get_history(self):
        return self.history.copy()

    def get_context_summary(self):
        if not self.history:
            return "无历史对话"
        turns = len(self.history) // 2
        return f"{turns}轮对话，最近: {self.history[-1]['content'][:30]}..."


# ============================================================
# JSON 提取函数（鲁棒）
# ============================================================
def extract_json(text: str):
    # 尝试直接解析
    try:
        return json.loads(text)
    except:
        pass

    # 提取所有 { ... } 块，选择最长的尝试
    candidates = re.findall(r"\{[\s\S]*?\}", text)
    for c in sorted(candidates, key=len, reverse=True):
        try:
            return json.loads(c)
        except:
            pass

    logger.warning(f"⚠️ JSON解析失败，输出内容: {text}")
    return {
        "age": 25,
        "gender": "unknown",
        "emotion": "neutral",
        "raw_output": text
    }


# ============================================================
# Qwen VLM 模型封装
# ============================================================
class QwenVLMModel:
    def __init__(self, model_path: str = MODEL_PATH):
        logger.info("🔧 正在加载 Qwen2.5-VL-3B-Instruct 模型...")
        logger.info(f"📂 模型路径: {model_path}")

        self.dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"🖥️ 设备: {self.device}, 数据类型: {self.dtype}")

        # 加载 Processor
        self.processor = AutoProcessor.from_pretrained(
            model_path,
            min_pixels=PIXELS,
            max_pixels=PIXELS,
            trust_remote_code=True,
            use_fast=False
        )

        # 加载模型
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_path,
            torch_dtype=self.dtype,
            device_map="auto",
            # attn_implementation="flash_attention_2",  # 加速注意力
            trust_remote_code=True
        ).eval()

        self.context = ContextManager(max_turns=10)
        logger.info("✅ Qwen2.5-VL 模型加载完成！")

    # ======================= 视觉推理 ===========================
    def inference(self, image: np.ndarray, text: str):
        logger.info("🧠 开始VLM推理...")
        logger.info(f"📝 用户输入: {text}")
        logger.info(f"📚 上下文: {self.context.get_context_summary()}")

        self.context.add_user(text)

        # ----------- 图像转换（OpenCV → PIL）-----------
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(image_rgb)

        # ----------- 构建 prompt（history 与视觉任务隔离）-----------
        history_context = ""
        if self.context.history:
            history_context += "### Conversation History\n"
            for msg in self.context.history[-6:]:
                role = "User" if msg["role"] == "user" else "Robot"
                history_context += f"{role}: {msg['content']}\n"
            history_context += "### End of History\n\n"

        query = (
            f"{history_context}"
            "### Visual Task\n"
            "Analyze the person in the image and output a JSON object:\n"
            "{\"age\": <int>, \"gender\": <male/female>, \"emotion\": <string>}."
        )

        # ----------- 构建消息（不再使用 file:// ）-----------
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": pil_image,
                     "resized_height": IMAGE_HEIGHT, "resized_width": IMAGE_WIDTH},
                    {"type": "text", "text": query},
                ]
            }
        ]

        text_prompt = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)

        inputs = self.processor(
            text=[text_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt"
        ).to(self.device)

        # ----------- 模型推理 -----------
        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=256,
                do_sample=False
            )

        trimmed = [o[len(i):] for i, o in zip(inputs.input_ids, outputs)]
        output_text = self.processor.batch_decode(trimmed, skip_special_tokens=True)[0]
        logger.info(f"📤 模型输出: {output_text}")

        analysis = extract_json(output_text)

        # ----------- 决定动作与回应 -----------
        decision = determine_action_and_response(analysis, text)
        self.context.add_assistant(decision["response_text"])

        return {
            "response_text": decision["response_text"],
            "action": decision["action"],
            "action_type": decision["action_type"],
            "emotion": decision["robot_emotion"],
            "confidence": 0.90,
            "analysis": analysis
        }


# ============================================================
# 机器人动作逻辑
# ============================================================
def gender_text(gender: str) -> str:
    if gender == "male": return "先生"
    if gender == "female": return "女士"
    return "朋友"


def determine_action_and_response(analysis: dict, user_text: str) -> dict:
    emotion = analysis.get("emotion", "").lower()
    response = ""
    action = "idle"
    action_type = "gesture"
    robot_emotion = "neutral"

    # ===== Emotion-based polite responses =====
    if "happy" in emotion:
        response = "You look happy today."
        action = "wave"
        robot_emotion = "happy"

    elif "sad" in emotion:
        response = "You seem a bit sad. I’m here if you need support."
        action = "nod"
        robot_emotion = "concerned"

    elif "angry" in emotion or "mad" in emotion:
        response = "I notice some signs of anger. Please take your time."
        action = "bow"
        robot_emotion = "apologetic"

    elif "surprise" in emotion:
        response = "You appear surprised."
        action = "thumbs_up"
        robot_emotion = "neutral"

    else:
        response = "Hello. It’s good to see you."
        action = "wave"
        robot_emotion = "friendly"

    # ===== Parse user commands (English only) =====
    u = user_text.lower()

    # Movement controls
    if "forward" in u or "move forward" in u:
        return {
            "response_text": "Moving forward.",
            "action": "forward",
            "action_type": "movement",
            "robot_emotion": robot_emotion
        }

    if "back" in u or "backward" in u:
        return {
            "response_text": "Moving backward.",
            "action": "backward",
            "action_type": "movement",
            "robot_emotion": robot_emotion
        }

    if "left" in u or "turn left" in u:
        return {
            "response_text": "Turning left.",
            "action": "turn_left",
            "action_type": "movement",
            "robot_emotion": robot_emotion
        }

    if "right" in u or "turn right" in u:
        return {
            "response_text": "Turning right.",
            "action": "turn_right",
            "action_type": "movement",
            "robot_emotion": robot_emotion
        }

    if "stop" in u or "halt" in u:
        return {
            "response_text": "Stopping now.",
            "action": "stop",
            "action_type": "system",
            "robot_emotion": robot_emotion
        }

    # Gesture controls
    if "wave" in u:
        return {
            "response_text": "Waving now.",
            "action": "wave",
            "action_type": "gesture",
            "robot_emotion": robot_emotion
        }

    if "nod" in u:
        return {
            "response_text": "Nodding.",
            "action": "nod",
            "action_type": "gesture",
            "robot_emotion": robot_emotion
        }

    return {
        "response_text": response,
        "action": action,
        "action_type": action_type,
        "robot_emotion": robot_emotion
    }

# ============================================================
# Flask 服务
# ============================================================
app = Flask(__name__)
vlm_model = None


@app.route("/infer", methods=["POST"])
def infer():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400

    text = data.get("text", data.get("asr_text", ""))
    image_b64 = data.get("image_base64", "")
    request_id = data.get("request_id", "unknown")

    logger.info("=" * 60)
    logger.info(f"📨 收到推理请求 ID={request_id}")

    if not image_b64:
        return jsonify({"status": "error", "message": "未收到图像"}), 400

    # 解码图像
    try:
        img_data = base64.b64decode(image_b64)
        nparr = np.frombuffer(img_data, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("cv2 decode returned None")
    except Exception as e:
        logger.error(f"❌ 图像解码失败: {e}")
        return jsonify({"status": "error", "message": "图像解码失败"}), 400

    result = vlm_model.inference(image, text)

    return jsonify({
        "status": "success",
        "text": result.get("response_text", ""),
        "action": result.get("action", ""),
        "action_type": result.get("action_type", ""),
        "emotion": result.get("emotion", "neutral"),
        "confidence": result.get("confidence", 0.0),
        "analysis": result.get("analysis", {}),
        "request_id": request_id
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "model_loaded": vlm_model is not None,
        "model_path": MODEL_PATH
    })


# ============================================================
# 启动服务器
# ============================================================
class ThorVLMServer:
    def __init__(self):
        global vlm_model
        vlm_model = QwenVLMModel()

    def run(self, host=HOST, port=PORT):
        logger.info("🚀 Thor VLM HTTP 服务器启动！")
        app.run(host=host, port=port, threaded=True)


def main():
    server = ThorVLMServer()
    server.run()


if __name__ == "__main__":
    main()