from ..common import LanProtocolCmd
from ..protocols.BaseLanProtocol import BaseLanProtocol


class HeartLanProtocol(BaseLanProtocol):

    def __init__(self):
        super().__init__()
        self.cmd = LanProtocolCmd.HEARTBEAT
