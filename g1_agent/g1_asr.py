import sys
import json
from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.std_msgs.msg.dds_._String_ import String_

def callback(msg):
    data = json.loads(msg.data)
    print(f"[ASR] 用户说: {data['text']} (置信度: {data['confidence']}) 角度: {data['angle']}°")

def main():
    if len(sys.argv) < 2:
        print(f"Usage: python3 {sys.argv[0]} networkInterface")
        sys.exit(0)

    net_if = sys.argv[1]
    ChannelFactoryInitialize(0, net_if)

    sub = ChannelSubscriber("rt/audio_msg", String_)
    sub.Init(callback)

    print("🚀 ASR 监听中... 对机器人说话吧！")
    while True:
        pass

if __name__ == "__main__":
    main()