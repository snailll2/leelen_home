import json
import threading
from typing import ClassVar, Optional

from ..common import LanProtocolCmd
from ..entity.dao.ConfigDao import ConfigDao
from ..entity.req.QueryModConfigReq import QueryModConfigReq
from ..protocols.BaseLanProtocol import BaseLanProtocol
from ..utils.LogUtils import LogUtils


class QueryModConfigLanProtocol(BaseLanProtocol):
    _instance: ClassVar[Optional['QueryModConfigLanProtocol']] = None
    _lock = threading.Lock()

    def __init__(self):
        if QueryModConfigLanProtocol._instance is not None:
            raise RuntimeError("Use instance() method to get the singleton instance")

        super().__init__()
        self.cmd = LanProtocolCmd.CONFIG_MOD_QUERY

    @classmethod
    def get_instance(cls) -> 'QueryModConfigLanProtocol':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def build_body(self) -> bool:
        """Build the protocol request body"""
        config_req = QueryModConfigReq()

        # config_req.T1 =
        config = ConfigDao.get_instance().get_config_by_gateway()
        config_req.T1 = config.latest_time if config else 0
        request_json = json.dumps(config_req.__dict__)

        LogUtils.i("QueryModConfigLanProtocol", f" 请求网关数据T1 t1 {config_req.T1} {self.cmd}  {request_json}")
        # Convert request to JSON
        # Set the request body
        self.request_data_body = request_json.encode('utf-8')
        return True
