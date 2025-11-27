import sys
sys.path.append("/home/unitree/unitree_sdk2_python")

import json
import time
import re
import openai

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.std_msgs.msg.dds_._String_ import String_
from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient

# ====== API KEY ======
openai.api_key = "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"

audio_client = None
last_talk_time = 0  # 节流控制（避免多次重复触发）


# ==========================================
#   ⭐ 上下文管理器（支持 10 轮）
# ==========================================
class ContextManager:
    def __init__(self, max_turns=10):
        self.max_turns = max_turns
        self.history = []          # 多轮对话历史
        self.scene = {}            # 预留：视觉上下文
        self.robot_state = {}      # 预留：机器人动作状态

    def add_user(self, text):
        self.history.append({"role": "user", "content": text})
        self._trim()

    def add_robot(self, text):
        self.history.append({"role": "assistant", "content": text})
        self._trim()

    def set_scene(self, info):
        self.scene = info

    def set_robot_state(self, state):
        self.robot_state = state

    def _trim(self):
        if len(self.history) > self.max_turns:
            self.history = self.history[-self.max_turns:]

    def build_prompt(self):
        """上下文给 GPT 使用，不朗读"""
        return {
            "history": self.history,
            "scene": self.scene,
            "robot_state": self.robot_state
        }


# 全局上下文
context = ContextManager()


# ===========================
#   文本过滤：防乱码
# ===========================
def is_valid_text(text: str) -> bool:
    """允许英文、数字、符号；过滤日文/俄文意外识别"""
    return re.match(r"^[\w\s\.,!?'\-]+$", text) is not None


# ===========================
#   ⭐ GPT 请求（包含上下文）
# ===========================
def gpt_reply(user_text: str) -> str:

    print(f"[GPT] Sending: {user_text}")

    # 1. 写入历史
    context.add_user(user_text)

    # 2. 当前完整上下文
    ctx = context.build_prompt()

    # ===========================
    #  SYSTEM PROMPT（禁止 GPT 复述上下文）
    # ===========================
    SYSTEM_PROMPT = """
    You are a friendly AI assistant living inside the Unitree G1 humanoid robot.

    Rules:
    - You NEVER output or repeat: history, scene, or robot_state.
    - These fields are ONLY for reasoning.
    - You respond ONLY to the user's latest message.
    - Always speak naturally and concisely.
    - Your reply MUST contain ONLY English alphabet letters.
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},

                # ⬇⬇⬇ 用 assistant 传递上下文，但模型不会朗读
                {
                    "role": "assistant",
                    "content": json.dumps(ctx)
                },

                # ⬇⬇⬇ 用户当前输入
                {
                    "role": "user",
                    "content": user_text
                }
            ]
        )

        reply = response["choices"][0]["message"]["content"]

        # 写入机器人回复
        context.add_robot(reply)

        print(f"[GPT] Reply: {reply}")
        return reply

    except Exception as e:
        print("[GPT ERROR]", e)
        return "Sorry, I am having trouble connecting to the cloud."


# ===========================
#        ASR 回调逻辑
# ===========================
def callback(msg: String_):
    global last_talk_time

    raw = msg.data if isinstance(msg.data, str) else msg.data()

    try:
        data = json.loads(raw)
    except Exception:
        print("[DEBUG] Not JSON:", raw)
        return

    if "text" not in data:
        return

    text = data["text"]
    conf = data.get("confidence", 0)

    # ========== 过滤 ==========
    if not text.strip():
        return

    if conf is not None and conf < 0.3:
        print(f"[FILTER] 置信度低({conf}) → 忽略: {text}")
        return

    if not is_valid_text(text):
        print(f"[FILTER] 可能乱码 → 忽略: {text}")
        # ⭐ 不 return，不打断节流（防死机）
        last_talk_time = time.time()
        return

    # ========== 节流 ==========
    now = time.time()
    if now - last_talk_time < 1.2:
        print("[FILTER] 触发过快 → 忽略")
        return

    last_talk_time = now

    # ========== 触发 GPT ==========
    print(f"[ASR] User said: {text}")
    reply = gpt_reply(text)

    # 输出到 G1 语音
    audio_client.TtsMaker(reply, 1)


# ===========================
#            主函数
# ===========================
def main():
    global audio_client

    if len(sys.argv) < 2:
        print(f"Usage: python3 {sys.argv[0]} networkInterface")
        sys.exit(0)

    net_if = sys.argv[1]

    ChannelFactoryInitialize(0, net_if)

    audio_client = AudioClient()
    audio_client.SetTimeout(10.0)
    audio_client.Init()

    sub = ChannelSubscriber("rt/audio_msg", String_)
    sub.Init(callback)

    print("🎤 G1 + GPT Multi-turn Assistant Started!")
    print("Speak to the robot!")

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()