import rclpy
from rclpy.node import Node

from command_listener import CommandListener
from action_executor import ActionExecutor
from text_speaker import TextSpeaker


class G1AgentNode(Node):
    def __init__(self):
        super().__init__("g1_agent")

        self.speaker = TextSpeaker()
        self.action_executor = ActionExecutor()

        # 监听器：收到 JSON 就回调 handle_cmd
        self.listener = CommandListener(self.handle_cmd)

        self.get_logger().info("G1 Agent Started!")

    def handle_cmd(self, data):
        # Handle text
        if "text" in data:
            self.speaker.speak(data["text"])

        # Handle action
        if "action" in data:
            self.action_executor.execute(data["action"])


def main(args=None):
    rclpy.init(args=args)
    node = G1AgentNode()
    rclpy.spin(node)
    rclpy.shutdown()