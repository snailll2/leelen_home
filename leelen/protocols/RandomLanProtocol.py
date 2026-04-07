import threading

from ..protocols.BaseLanProtocol import BaseLanProtocol
from ..common import LanProtocolCmd, ProtocolDefault


class RandomLanProtocol(BaseLanProtocol):
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        super().__init__()
        self.cmd = LanProtocolCmd.RANDOM_CODE
        self.encrypted = ProtocolDefault.LAN_NO_ENCRYPT
        self.server_id = ProtocolDefault.DEFAULT_LAN_SERVER_ID

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = RandomLanProtocol()
        return cls._instance
