from ..common import WanProtocolCmd
from ..protocols.BaseWanProtocol import BaseWanProtocol


class HeartWanProtocol(BaseWanProtocol):

    def __init__(self):
        super().__init__()
        self.cmd = WanProtocolCmd.HEARTBEAT
