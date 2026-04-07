import threading

from ..common import WanProtocolCmd
from ..protocols.BaseWanProtocol import BaseWanProtocol


class HeartWanProtocol(BaseWanProtocol):
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        super().__init__()
        self.cmd = WanProtocolCmd.HEARTBEAT

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = HeartWanProtocol()
        return cls._instance
