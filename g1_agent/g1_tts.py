import sys
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient

def detect_english(s):
    return any('a' <= c.lower() <= 'z' for c in s)

def main():
    if len(sys.argv) < 3:
        print(f"Usage: python3 {sys.argv[0]} networkInterface \"text to speak\"")
        sys.exit(-1)

    net_if = sys.argv[1]
    text = sys.argv[2]

    ChannelFactoryInitialize(0, net_if)

    audio = AudioClient()
    audio.SetTimeout(10.0)
    audio.Init()

    # 判断语言并设置 speaker
    if detect_english(text):
        speaker = 1   # 英文角色
    else:
        speaker = 0   # 中文角色

    print(f"G1 说({['中文','英文'][speaker]}): {text}")
    audio.TtsMaker(text, speaker)

if __name__ == "__main__":
    main()