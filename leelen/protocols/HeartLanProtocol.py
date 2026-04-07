from threading import Lock

from ..common import LanProtocolCmd
from ..protocols.BaseLanProtocol import BaseLanProtocol


class HeartLanProtocol(BaseLanProtocol):
    _instance = None
    _lock = Lock()

    def __init__(self):
        super().__init__()
        self.cmd = LanProtocolCmd.HEARTBEAT

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = cls()
        return cls._instance
