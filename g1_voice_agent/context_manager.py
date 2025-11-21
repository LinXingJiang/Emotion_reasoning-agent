# context_manager.py
import time

class ContextManager:
    def __init__(self, max_turns=15):
        self.max_turns = max_turns
        self.history = []        # 多轮对话
        self.scene = {}          # 摄像头 / VLM 场景
        self.robot_state = {}    # 姿态、手势等

    def add_user(self, text):
        self.history.append({"role": "user", "content": text, "time": time.time()})
        self._trim()

    def add_robot(self, text):
        self.history.append({"role": "assistant", "content": text, "time": time.time()})
        self._trim()

    def set_scene(self, data):
        self.scene = data

    def set_robot_state(self, data):
        self.robot_state = data

    def build_prompt(self):
        return {
            "history": self.history,
            "scene": self.scene,
            "robot_state": self.robot_state
        }

    def _trim(self):
        if len(self.history) > self.max_turns:
            self.history = self.history[-self.max_turns:]