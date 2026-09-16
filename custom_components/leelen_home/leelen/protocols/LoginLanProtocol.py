import json

from ..common import LanProtocolCmd
from ..entity.ack.LoginAck import LoginAck
from ..protocols.BaseLanProtocol import BaseLanProtocol


class LoginLanProtocol(BaseLanProtocol):

    def __init__(self):
        super().__init__()
        self.cmd = LanProtocolCmd.APP_LOGON
        self._login_req = None

    def build_body(self):
        if self._login_req is None:
            return False
        self.request_data_body = json.dumps(self._login_req.to_dict()).replace(" ", "").encode()
        return True

    def get_login_lan_ack(self, protocol):
        return LoginAck(**json.loads(protocol.request_data_body))

    def set_login_req(self, login_req):
        self._login_req = login_req
