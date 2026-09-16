from ..protocols.BaseLanProtocol import BaseLanProtocol
from ..common import LanProtocolCmd, ProtocolDefault


class RandomLanProtocol(BaseLanProtocol):

    def __init__(self):
        super().__init__()
        self.cmd = LanProtocolCmd.RANDOM_CODE
        self.encrypted = ProtocolDefault.LAN_NO_ENCRYPT
        self.server_id = ProtocolDefault.DEFAULT_LAN_SERVER_ID
