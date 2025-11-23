import sys
sys.path.append("/home/unitree/unitree_sdk2_python")

import json
import time
import re
import openai

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.std_msgs.msg.dds_._String_ import String_
from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient

# ====== API KEY 直接写在代码里 ======
openai.api_key = "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"


audio_client = None
last_talk_time = 0  # 节流控制（避免多次重复触发）

# ===========================
#   文本过滤：防乱码
# ===========================
def is_valid_text(text: str) -> bool:
    """允许英文、数字、符号；过滤日文/俄文意外识别"""
    return re.match(r"^[\w\s\.,!?'\-]+$", text) is not None


# ===========================
#       GPT 请求函数
# ===========================
def gpt_reply(text: str) -> str:
    """Call GPT using openai==1.x ChatCompletion API"""
    print(f"[GPT] Sending: {text}")

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system",
                 "content": "You are a friendly AI assistant living inside the Unitree G1 humanoid robot."},
                {"role": "user", "content": text}
            ]
        )

        reply = response["choices"][0]["message"]["content"]
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
    angle = data.get("angle", -1)

    # ===========================
    #       过滤规则（不删）
    # ===========================

    if not text.strip():
        print("[FILTER] 空文本 → 忽略")
        return

    # 宇树 ASR confidence 只有 0.5，适当降低阈值
    MIN_CONFIDENCE = 0.3
    if conf is not None and conf < MIN_CONFIDENCE:
        print(f"[FILTER] 置信度过低({conf}) → 忽略: {text}")
        return

    if not is_valid_text(text):
        print(f"[FILTER] 文本可能乱码 → 忽略: {text}")
        return

    # ⚠️ 这里：已移除 is_final 过滤
    # if not is_final:
    #     print(...)
    #     return

    # 节流：1.2秒内不重复
    now = time.time()
    if now - last_talk_time < 1.2:
        print("[FILTER] 触发过快 → 忽略")
        return
    last_talk_time = now

    # ===========================
    #     通过所有过滤 → 触发
    # ===========================
    print(f"[ASR] User said: {text} (conf={conf}, angle={angle})")

    reply = gpt_reply(text)

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

    print("🎤 G1 + GPT Voice Assistant Started! (No is_final filter)")
    print("Speak to the robot!")

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()