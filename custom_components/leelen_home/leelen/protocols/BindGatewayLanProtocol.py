import json
from typing import Optional

from ..protocols.BaseLanProtocol import BaseLanProtocol
from ..entity.req.BindGatewayReq import BindGatewayReq
from ..common import LanProtocolCmd
from ..utils.LogUtils import LogUtils


class BindGatewayLanProtocol(BaseLanProtocol):
    def __init__(self):
        super().__init__()
        self.cmd = LanProtocolCmd.BIND_GATEWAY
        self._bind_gateway_req: Optional[BindGatewayReq] = None

    def build_body(self) -> bool:
        if self._bind_gateway_req is not None:
            payload = json.dumps(self._bind_gateway_req.__dict__)
            LogUtils.d(f"build_body() payload: {payload}")
            self.request_data_body = payload.encode('utf-8')
        return True

    def set_bind_req(self, bind_req: BindGatewayReq) -> None:
        self._bind_gateway_req = bind_req

    @property
    def bind_gateway_req(self) -> Optional[BindGatewayReq]:
        return self._bind_gateway_req

    @bind_gateway_req.setter
    def bind_gateway_req(self, value: BindGatewayReq):
        self._bind_gateway_req = value
