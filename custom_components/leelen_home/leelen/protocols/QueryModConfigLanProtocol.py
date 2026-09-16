import json

from ..common import LanProtocolCmd
from ..entity.dao.ConfigDao import ConfigDao
from ..entity.req.QueryModConfigReq import QueryModConfigReq
from ..protocols.BaseLanProtocol import BaseLanProtocol
from ..utils.LogUtils import LogUtils


class QueryModConfigLanProtocol(BaseLanProtocol):

    def __init__(self):
        super().__init__()
        self.cmd = LanProtocolCmd.CONFIG_MOD_QUERY

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
