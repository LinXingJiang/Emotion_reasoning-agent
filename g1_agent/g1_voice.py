import sys
import json
import time

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.std_msgs.msg.dds_._String_ import String_
from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient


audio_client = None  # global TTS client


def callback(msg: String_):

    # ---- FIXED: msg.data MAY be a function or a string ----
    raw = msg.data if isinstance(msg.data, str) else msg.data()

    try:
        data = json.loads(raw)
    except Exception:
        print("[DEBUG] Non-JSON:", raw)
        return

    # Must contain ASR text
    if "text" not in data:
        return

    text = data["text"]
    conf = data.get("confidence")
    angle = data.get("angle")

    print(f"[ASR] User said: {text} (confidence={conf}, angle={angle}°)")

    # ===== Conversation Logic =====
    t = text.lower()

    if "hello" in t or "hi" in t:
        audio_client.TtsMaker("Hello! Nice to meet you!", 1)

    elif "who are you" in t:
        audio_client.TtsMaker("I am your Unitree G1 robot assistant.", 1)

    elif "how are you" in t:
        audio_client.TtsMaker("I am doing well. How can I help you?", 1)

    elif "good morning" in t:
        audio_client.TtsMaker("Good morning! I hope you have a great day!", 1)

    elif "thank you" in t:
        audio_client.TtsMaker("You're welcome!", 1)

    # Fallback: repeat
    else:
        audio_client.TtsMaker(f"You said: {text}", 1)



def main():
    global audio_client

    if len(sys.argv) < 2:
        print(f"Usage: python3 {sys.argv[0]} networkInterface")
        sys.exit(0)

    net_if = sys.argv[1]

    ChannelFactoryInitialize(0, net_if)

    # Init TTS
    audio_client = AudioClient()
    audio_client.SetTimeout(10.0)
    audio_client.Init()

    # Subscribe ASR
    sub = ChannelSubscriber("rt/audio_msg", String_)
    sub.Init(callback)

    print("🎤 Dialogue Agent started. Speak to the robot!")

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()