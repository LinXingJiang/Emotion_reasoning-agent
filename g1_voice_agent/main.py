# main.py
# -------------------------------
# 主调度程序：只负责初始化和注册回调
# 所有逻辑由 ASR 驱动（用户说话 → 才执行后续）
# -------------------------------

import time

# === 引入你的模块（按你的项目结构） ===
from context_manager import ContextManager
from llm_client import GPTClient
from asr_module import init_asr
from tts_module import TTS
from action_executor import execute_gesture

# 视觉模块（预留）
from vision.camera import Camera
from vision.scene_analyzer import SceneAnalyzer


# ============================================================
# ASR 回调：—— 整个系统逻辑的唯一入口（用户说话触发）
# ============================================================

def on_asr(text):
    global context, llm, tts, camera, scene_analyzer

    print(f"[ASR] 用户说：{text}")

    # 1. 写入用户输入到上下文
    context.add_user(text)

    # 2. 视觉捕获（可选）
    frame = camera.capture()
    scene_info = scene_analyzer.analyze(frame)
    context.set_scene(scene_info)

    # 3. 构建 Prompt → 调用 GPT JSON Agent
    prompt_bundle = context.build_prompt()
    reply = llm.chat(prompt_bundle)

    # reply = { "say": "...", "gesture": "...", "safety": "ok" }

    # 4. 动作 & 语言输出
    say_text = reply.get("say", "")
    gesture = reply.get("gesture", "idle")

    if say_text:
        print(f"[Robot] 说：{say_text}")
        tts.say(say_text)

    print(f"[Robot] 执行动作：{gesture}")
    execute_gesture(gesture)

    # 5. 将机器人回复写入上下文
    context.add_robot(say_text)
    context.set_robot_state({"gesture": gesture})


# ============================================================
# 主函数（仅负责初始化和保持主线程）
# ============================================================

def main(): 
    global context, llm, tts, camera, scene_analyzer

    print("===== 启动 G1 智能 Agent 系统 =====")

    # 初始化上下文管理
    context = ContextManager()

    # 初始化 LLM（GPT JSON Agent）
    llm = GPTClient()

    # 初始化语音合成（TTS）
    tts = TTS()

    # 初始化视觉模块（预留）
    camera = Camera()
    scene_analyzer = SceneAnalyzer()

    # 初始化 ASR 订阅（注册回调）
    init_asr(on_asr)

    print("🚀 系统已准备好。请开始对机器人说话。")

    # 主线程保持运行
    while True:
        time.sleep(1)


# 入口
if __name__ == "__main__":
    main()