"""
Thor VLM 推理服务器 - 基于Qwen2.5-VL-3B-Instruct
功能: 接收G1发送的图像和文本，进行VLM推理，返回响应
模型: Qwen2.5-VL-3B-Instruct (人物分析、情感识别)
"""

import json
import logging
import base64
import numpy as np
import cv2
import torch
import io
import re
from typing import Optional
from PIL import Image

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber, ChannelPublisher
from unitree_sdk2py.idl.std_msgs.msg.dds_._String_ import String_

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
NETWORK_INTERFACE = "eth0"  # Thor的网络接口，根据实际情况修改
RECV_TOPIC = "rt/thor_request"   # 接收G1请求的话题
SEND_TOPIC = "rt/thor_response"  # 发送响应的话题

# Qwen2.5-VL 模型配置
MODEL_PATH = "/home/bryce/models/Qwen2.5-VL-3B-Instruct"
IMAGE_HEIGHT = 280
IMAGE_WIDTH = 420
PIXELS = IMAGE_HEIGHT * IMAGE_WIDTH


# ============================================================
# 上下文管理器（支持多轮对话）
# ============================================================
class ContextManager:
    """
    多轮对话上下文管理器
    保持最近N轮的对话历史，支持连贯对话
    """
    
    def __init__(self, max_turns: int = 10):
        """
        初始化上下文管理器
        
        参数:
            max_turns: 最大保留的对话轮数（默认10轮）
        """
        self.max_turns = max_turns
        self.history = []  # 对话历史: [{"role": "user"/"assistant", "content": "..."}]
        logger.info(f"📚 上下文管理器初始化: 最大保留 {max_turns} 轮对话")
    
    def add_user(self, text: str):
        """添加用户消息到历史"""
        self.history.append({"role": "user", "content": text})
        self._trim()
        logger.debug(f"➕ 添加用户消息: {text[:50]}...")
    
    def add_assistant(self, text: str):
        """添加机器人回复到历史"""
        self.history.append({"role": "assistant", "content": text})
        self._trim()
        logger.debug(f"➕ 添加机器人回复: {text[:50]}...")
    
    def _trim(self):
        """保持历史在最大轮数内"""
        if len(self.history) > self.max_turns * 2:  # 每轮包含user+assistant
            removed = len(self.history) - self.max_turns * 2
            self.history = self.history[-self.max_turns * 2:]
            logger.debug(f"🗑️  移除最早的 {removed} 条消息")
    
    def get_history(self) -> list:
        """获取当前对话历史"""
        return self.history.copy()
    
    def get_context_summary(self) -> str:
        """获取上下文摘要（用于日志）"""
        if not self.history:
            return "无历史对话"
        turns = len(self.history) // 2
        return f"{turns}轮对话，最近: {self.history[-1]['content'][:30]}..."
    
    def clear(self):
        """清空历史（可选功能）"""
        self.history = []
        logger.info("🗑️  上下文已清空")


# ============================================================
# Qwen VLM 模型封装
# ============================================================
class QwenVLMModel:
    """
    Qwen2.5-VL 模型封装
    支持图像+文本输入，输出结构化JSON响应
    支持多轮对话上下文
    """
    
    def __init__(self, model_path: str = MODEL_PATH):
        """
        初始化Qwen VLM模型
        
        参数:
            model_path: Qwen2.5-VL模型路径
        """
        logger.info("🔧 正在加载 Qwen2.5-VL-3B-Instruct 模型...")
        logger.info(f"📂 模型路径: {model_path}")
        
        # 设置数据类型
        self.dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        logger.info(f"🖥️  设备: {self.device}, 数据类型: {self.dtype}")
        
        # 加载processor
        logger.info("📦 加载 Processor...")
        self.processor = AutoProcessor.from_pretrained(
            model_path,
            min_pixels=PIXELS,
            max_pixels=PIXELS,
            trust_remote_code=True,
            use_fast=False
        )
        
        # 加载模型
        logger.info("🧠 加载 VLM 模型...")
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_path,
            torch_dtype=self.dtype,
            device_map="auto",
            trust_remote_code=True
        ).eval()
        
        # 初始化上下文管理器
        self.context = ContextManager(max_turns=10)
        
        logger.info("✅ Qwen2.5-VL 模型加载完成！")
    
    def _parse_json_response(self, text: str) -> dict:
        """
        从模型输出中提取JSON
        
        参数:
            text: 模型输出的文本
        
        返回:
            解析后的字典
        """
        try:
            # 尝试直接解析
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试提取JSON部分
            # 查找 {...} 模式
            json_match = re.search(r'\{[^}]+\}', text)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except:
                    pass
            
            # 解析失败，返回默认结构
            logger.warning(f"⚠️ JSON解析失败，原始输出: {text}")
            return {
                "age": 25,
                "gender": "unknown",
                "emotion": "neutral",
                "raw_output": text
            }
    
    def _determine_action_and_response(self, analysis: dict, user_text: str) -> dict:
        """
        根据分析结果和用户输入，决定机器人的回复和动作
        
        参数:
            analysis: VLM分析结果 {"age": int, "gender": str, "emotion": str}
            user_text: 用户说的话
        
        返回:
            {
                "response_text": str,    # 机器人要说的话
                "action": str,           # 动作名称
                "action_type": str,      # 动作类型
                "robot_emotion": str     # 机器人表达的情感
            }
        """
        age = analysis.get("age", 25)
        gender = analysis.get("gender", "unknown")
        emotion = analysis.get("emotion", "neutral")
        
        # 根据用户情感决定机器人响应
        emotion_lower = emotion.lower()
        
        # 情感映射到回复和动作
        if "happy" in emotion_lower or "joy" in emotion_lower or "smile" in emotion_lower:
            response_text = f"你看起来很开心呢！让我们一起开心吧。"
            action = "wave"
            action_type = "gesture"
            robot_emotion = "happy"
        
        elif "sad" in emotion_lower or "unhappy" in emotion_lower or "down" in emotion_lower:
            response_text = f"你看起来有点不开心，需要我做点什么让你开心吗？"
            action = "nod"
            action_type = "gesture"
            robot_emotion = "concerned"
        
        elif "angry" in emotion_lower or "mad" in emotion_lower:
            response_text = f"我感觉到你有点生气，让我们冷静一下吧。"
            action = "bow"
            action_type = "gesture"
            robot_emotion = "apologetic"
        
        elif "surprise" in emotion_lower or "shocked" in emotion_lower:
            response_text = f"哇，看起来发生了什么让你惊讶的事情！"
            action = "thumbs_up"
            action_type = "gesture"
            robot_emotion = "excited"
        
        else:  # neutral or other
            response_text = f"你好！很高兴见到你。"
            action = "wave"
            action_type = "gesture"
            robot_emotion = "friendly"
        
        # 根据用户说的话进一步调整
        user_lower = user_text.lower()
        
        if "你好" in user_text or "hello" in user_lower or "hi" in user_lower:
            response_text = f"你好！我看到你了，{gender_text(gender)}。" + response_text
            action = "wave"
        
        elif "前进" in user_text or "forward" in user_lower or "走" in user_text:
            response_text = "好的，我现在向前移动。"
            action = "forward"
            action_type = "movement"
        
        elif "停" in user_text or "stop" in user_lower:
            response_text = "好的，我停下来了。"
            action = "stop"
            action_type = "system"
        
        elif "挥手" in user_text or "wave" in user_lower:
            response_text = "好的，我向你挥手！"
            action = "wave"
            action_type = "gesture"
        
        elif "点头" in user_text or "nod" in user_lower:
            response_text = "明白了！"
            action = "nod"
            action_type = "gesture"
        
        return {
            "response_text": response_text,
            "action": action,
            "action_type": action_type,
            "robot_emotion": robot_emotion
        }
    
    def inference(self, image: np.ndarray, text: str) -> dict:
        """
        执行VLM推理（支持多轮对话上下文）
        
        参数:
            image: OpenCV格式的图像 (BGR, numpy array)
            text: 用户输入的文本
        
        返回:
            {
                "response_text": "机器人要说的话",
                "action": "wave",
                "action_type": "gesture",
                "emotion": "happy",
                "confidence": 0.95,
                "analysis": {"age": 25, "gender": "male", "emotion": "happy"}
            }
        """
        logger.info(f"🧠 开始VLM推理（多轮对话）...")
        logger.info(f"📝 用户输入: '{text}'")
        logger.info(f"📚 当前上下文: {self.context.get_context_summary()}")
        logger.info(f"📷 图像尺寸: {image.shape}")
        
        try:
            # 1. 添加用户消息到历史
            self.context.add_user(text)
            
            # 2. 转换图像格式 (OpenCV BGR -> PIL RGB)
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(image_rgb)
            
            # 3. 保存临时图像（Qwen需要文件路径）
            temp_image_path = "/tmp/thor_temp_image.jpg"
            pil_image.save(temp_image_path)
            img_path = f"file://{temp_image_path}"
            
            # 4. 构建prompt - 包含上下文和当前任务
            history_context = ""
            if self.context.history:
                history_context = "\n\n--- Recent Conversation History ---\n"
                for msg in self.context.history[-6:]:  # 最近3轮（6条消息）
                    role = "User" if msg["role"] == "user" else "Robot"
                    history_context += f"{role}: {msg['content']}\n"
                history_context += "--- End of History ---\n\n"
            
            query = (
                f"{history_context}"
                f"Current user input: '{text}'\n\n"
                "Please analyze the person in this image. "
                "Estimate their approximate age (in years), gender, and emotional state "
                "based on visual cues. "
                "Output the result in JSON format as: "
                "{\"age\": <int>, \"gender\": <male/female>, \"emotion\": <string>}."
            )
            
            # 5. 构建消息
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "image": img_path,
                            "resized_height": IMAGE_HEIGHT,
                            "resized_width": IMAGE_WIDTH
                        },
                        {"type": "text", "text": query}
                    ]
                }
            ]
            
            # 6. 处理输入
            text_prompt = self.processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = self.processor(
                text=[text_prompt],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt"
            ).to(self.device)
            
            # 7. 推理
            logger.info("⚡ 执行模型推理...")
            with torch.inference_mode():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=256,
                    do_sample=False
                )
            
            # 8. 解码输出
            trimmed = [o[len(i):] for i, o in zip(inputs.input_ids, outputs)]
            output_text = self.processor.batch_decode(
                trimmed, skip_special_tokens=True
            )[0]
            
            logger.info(f"📤 模型原始输出: {output_text}")
            
            # 9. 解析JSON
            analysis = self._parse_json_response(output_text)
            logger.info(f"📊 分析结果: {analysis}")
            
            # 10. 决定机器人的回复和动作（考虑上下文）
            decision = self._determine_action_and_response(analysis, text)
            
            # 11. 添加机器人回复到历史
            self.context.add_assistant(decision["response_text"])
            
            # 12. 构建最终响应
            result = {
                "response_text": decision["response_text"],
                "action": decision["action"],
                "action_type": decision["action_type"],
                "emotion": decision["robot_emotion"],
                "confidence": 0.90,
                "analysis": analysis
            }
            
            logger.info(f"✅ 推理完成: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ VLM推理失败: {e}", exc_info=True)
            # 返回默认响应
            return {
                "response_text": f"我听到你说：{text}",
                "action": "nod",
                "action_type": "gesture",
                "emotion": "neutral",
                "confidence": 0.5,
                "error": str(e)
            }


def gender_text(gender: str) -> str:
    """性别文本转换"""
    if gender == "male":
        return "先生"
    elif gender == "female":
        return "女士"
    else:
        return "朋友"


# ============================================================
# Thor服务器主类
# ============================================================
class ThorVLMServer:
    """Thor VLM推理服务器"""
    
    def __init__(self, network_interface: str):
        self.network_interface = network_interface
        self.vlm_model = QwenVLMModel()
        self.subscriber: Optional[ChannelSubscriber] = None
        self.publisher: Optional[ChannelPublisher] = None
    
    def initialize(self) -> bool:
        """初始化ROS2通信"""
        try:
            logger.info("=" * 60)
            logger.info("🖥️  Thor VLM服务器 - 正在初始化")
            logger.info("=" * 60)
            
            # 初始化ROS2 DDS
            logger.info(f"📡 初始化ROS2 DDS，网络接口: {self.network_interface}")
            ChannelFactoryInitialize(0, self.network_interface)
            
            # 创建订阅者（接收G1的请求）
            logger.info(f"📥 订阅话题: {RECV_TOPIC}")
            self.subscriber = ChannelSubscriber(RECV_TOPIC, String_)
            self.subscriber.Init(self._on_request)
            
            # 创建发布者（发送响应给G1）
            logger.info(f"📤 创建发布者: {SEND_TOPIC}")
            self.publisher = ChannelPublisher(SEND_TOPIC, String_)
            self.publisher.Init()
            
            logger.info("=" * 60)
            logger.info("✅ Thor VLM服务器初始化成功！")
            logger.info("=" * 60)
            return True
            
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}", exc_info=True)
            return False
    
    def _on_request(self, msg: String_) -> None:
        """
        处理G1发来的推理请求
        """
        try:
            # 解析JSON数据
            raw_data = msg.data if isinstance(msg.data, str) else msg.data()
            data = json.loads(raw_data)
            
            text = data.get("text", data.get("asr_text", ""))
            image_b64 = data.get("image_base64", "")
            request_id = data.get("request_id", "unknown")
            timestamp = data.get("timestamp", 0)
            
            logger.info("=" * 60)
            logger.info(f"📨 收到请求 (ID: {request_id[:8]}...)")
            logger.info(f"📝 文本: '{text}'")
            logger.info(f"⏱️  时间戳: {timestamp}")
            
            # 解码图像
            image = None
            if image_b64:
                try:
                    img_data = base64.b64decode(image_b64)
                    nparr = np.frombuffer(img_data, np.uint8)
                    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    logger.info(f"📷 图像解码成功: {image.shape}")
                except Exception as e:
                    logger.warning(f"⚠️ 图像解码失败: {e}")
                    # 使用空白图像
                    image = np.zeros((IMAGE_HEIGHT, IMAGE_WIDTH, 3), dtype=np.uint8)
            else:
                logger.warning("⚠️ 未收到图像，使用空白图像")
                image = np.zeros((IMAGE_HEIGHT, IMAGE_WIDTH, 3), dtype=np.uint8)
            
            # VLM推理
            result = self.vlm_model.inference(image, text)
            
            # 构建响应
            response = {
                "status": "success",
                "text": result["response_text"],
                "action": result["action"],
                "action_type": result["action_type"],
                "emotion": result["emotion"],
                "confidence": result["confidence"],
                "request_id": request_id,
                "analysis": result.get("analysis", {})
            }
            
            # 发送响应
            self._send_response(response)
            logger.info(f"✅ 响应已发送 (ID: {request_id[:8]}...)")
            logger.info("=" * 60)
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON解析失败: {e}")
            self._send_error_response("json_parse_error", request_id="unknown")
        except Exception as e:
            logger.error(f"❌ 请求处理失败: {e}", exc_info=True)
            self._send_error_response(
                str(e),
                request_id=data.get("request_id", "unknown") if 'data' in locals() else "unknown"
            )
    
    def _send_response(self, response: dict) -> None:
        """发送响应给G1"""
        try:
            msg = String_()
            msg.data = json.dumps(response, ensure_ascii=False)
            self.publisher.Write(msg)
            logger.debug(f"📡 发送响应: {json.dumps(response, ensure_ascii=False)[:200]}...")
        except Exception as e:
            logger.error(f"❌ 发送响应失败: {e}")
    
    def _send_error_response(self, error_msg: str, request_id: str) -> None:
        """发送错误响应"""
        response = {
            "status": "error",
            "error": error_msg,
            "text": "抱歉，处理请求时出现错误。",
            "request_id": request_id,
            "action": "shake_head",
            "action_type": "gesture",
            "confidence": 0.0
        }
        self._send_response(response)
    
    def run(self):
        """运行服务器（保持运行状态）"""
        logger.info("=" * 60)
        logger.info("🚀 Thor VLM服务器 - 运行中")
        logger.info("🎯 等待G1请求...")
        logger.info("⌨️  按 Ctrl+C 停止服务器")
        logger.info("=" * 60)
        
        try:
            import time
            while True:
                time.sleep(0.1)  # 主循环，ROS2回调在后台线程处理
        except KeyboardInterrupt:
            logger.info("\n⏹️  收到停止信号 (Ctrl+C)")
            self.stop()
    
    def stop(self):
        """停止服务器"""
        logger.info("=" * 60)
        logger.info("🛑 正在停止 Thor VLM服务器")
        logger.info("=" * 60)
        # 清理资源
        if self.subscriber:
            self.subscriber = None
        if self.publisher:
            self.publisher = None
        logger.info("✅ Thor VLM服务器已停止")


# ============================================================
# 主程序入口
# ============================================================
def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Thor VLM推理服务器 (基于Qwen2.5-VL-3B-Instruct)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python thor_vlm_server.py eth0
  python thor_vlm_server.py wlan0 --debug

注意:
  - 确保Qwen2.5-VL模型路径正确: {MODEL_PATH}
  - 确保与G1机器人在同一网络
  - 推荐使用GPU加速 (CUDA)
        """.format(MODEL_PATH=MODEL_PATH)
    )
    
    parser.add_argument(
        "network_interface",
        help="网络接口名称 (例如: eth0, wlan0)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="开启调试日志",
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("🐛 调试模式已启用")
    
    # 显示系统信息
    logger.info("=" * 60)
    logger.info("🔧 系统信息")
    logger.info("=" * 60)
    logger.info(f"🖥️  CUDA可用: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        logger.info(f"🎮 GPU设备: {torch.cuda.get_device_name(0)}")
        logger.info(f"💾 GPU内存: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
    logger.info(f"📂 模型路径: {MODEL_PATH}")
    logger.info(f"📐 图像尺寸: {IMAGE_WIDTH}x{IMAGE_HEIGHT}")
    logger.info("=" * 60)
    
    # 创建并运行服务器
    server = ThorVLMServer(args.network_interface)
    
    if not server.initialize():
        logger.error("❌ 初始化失败")
        return 1
    
    server.run()
    return 0


if __name__ == "__main__":
    exit(main())
