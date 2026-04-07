import json
import threading
from typing import Optional

from ..common import LanProtocolCmd
from ..entity.req.FetchConfigModReq import FetchConfigModReq
from ..protocols.BaseLanProtocol import BaseLanProtocol


class FetchModConfigLanProtocol(BaseLanProtocol):
    _instance: Optional['FetchModConfigLanProtocol'] = None
    _lock = threading.Lock()

    def __init__(self):
        super().__init__()
        self.cmd = LanProtocolCmd.CONFIG_MOD_FETCH
        self.m_fetch_config_mod_req: Optional[FetchConfigModReq] = None
        # self.is_add_sub=True

    @classmethod
    def get_instance(cls) -> 'FetchModConfigLanProtocol':
        with cls._lock:
            if not cls._instance:
                cls._instance = FetchModConfigLanProtocol()
            return cls._instance

    def build_body(self) -> bool:
        if hasattr(self, 'm_fetch_config_mod_req') and self.m_fetch_config_mod_req is not None:
            self.request_data_body = json.dumps(self.m_fetch_config_mod_req.to_dict()).encode('utf-8')
        else:
            super().build_body()
        return True

    def set_fetch_config_mod_req(self, req: FetchConfigModReq) -> None:
        self.m_fetch_config_mod_req = req
