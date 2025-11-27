import json
from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.std_msgs.msg.dds_._String_ import String_

class CommandListener:
    def __init__(self, callback):
        """
        callback(data: dict)
        """
        ChannelFactoryInitialize()
        self.sub = ChannelSubscriber(
            "/jetson_command",
            String_,
            self._on_rx
        )
        self.callback = callback

    def _on_rx(self, msg: String_):
        try:
            data = json.loads(msg.data)
            self.callback(data)
        except:
            print("Invalid JSON received")