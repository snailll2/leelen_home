import json
import threading
from typing import Dict, Any, List

from ..common import LeelenConst
from ..common.FrameIdSingleton import frame_id_counter
from ..common.LeelenType import GatewayTable, TableOperateType
from ..common.SingletonMixin import SingletonMixin
from ..entity.GatewayInfo import GatewayInfo
from ..entity.ConfigModifyInfo import ConfigModifyInfo
from ..entity.Message import Message
from ..entity.ack.FetchConfigModAck import FetchConfigModAck
from ..entity.ack.ModInfo import ModInfo
from ..entity.dao.AckToDao import AckToDao
from ..entity.dao.ConfigDao import ConfigDao
from ..entity.req.FetchConfigModReq import FetchConfigModReq
from ..models.LanDataRequestModel import LanDataRequestModel
from ..protocols.BaseLanProtocol import BaseLanProtocol
from ..protocols.DeviceStatusLanProtocol import DeviceStatusLanProtocol
from ..utils.ConvertUtils import ConvertUtils
from ..utils.LogUtils import LogUtils



class LanDataResponseHandleModel(SingletonMixin):
    TAG = "LanDataResponseHandleModel"

    def __init__(self):
        self.config_req_table_name_list = []
        self.m_change_table_name_list = []
        self.is_expired = False
        self._lock = threading.Lock()
        self.m_lan_data_request_model = LanDataRequestModel.get_instance()

    def add_req_by_type(self, t1, t2, tbl, req_type, num):
        req = FetchConfigModReq()
        req.T1 = t1
        req.T2 = t2
        req.tbl = tbl
        req.type = req_type
        req.num = num if num < 100 else 100
        return req

    def handle_random_key_response(self, base_lan_protocol, handler):
        LogUtils.d(self.TAG, "handle_random_key_response()")

        # 假设 base_lan_protocol.request_data_body 是 JSON 字符串
        data = json.loads(base_lan_protocol.request_data_body)
        random = data.get("random")  # 相当于 RandomAck.random

        # 网关拒绝时会返回 {"ack": 255}(无 random 字段)。把 ack 打出来,
        # 便于在日志里区分「网关拒绝」与「正常返回 random」。
        ack = data.get("ack")
        if ack is not None and ack != 1:
            LogUtils.w(self.TAG, f"gateway REJECTED random-key request, ack={ack} (body={data})")
        else:
            LogUtils.d(self.TAG, f"handle_random_key_response(): {random}")

        # 创建并发送消息
        msg = Message(what=1, obj=random)
        handler.send(msg)

    def handle_login_lan_response(self, protocol, handler):
        """
        :param protocol: BaseLanProtocol 实例，包含 requestDataBody 和 serverId
        :param handler: handler 对象，需要实现 send() 方法（可模拟 Handler）
        """
        # 假设 protocol.requestDataBody 是 JSON 字符串
        try:
            parsed = json.loads(protocol.request_data_body)
            ack = parsed.get("ack", 0)
        except Exception as e:
            LogUtils.e(e)
            ack = 0

        LogUtils.d(f"login success ? = {ack}")
        LogUtils.d(f"login success ? = {protocol.__dict__}")
        # LogUtils.d(f"login success ? = {parsed}")

        GatewayInfo.get_instance().tcp_server_code = protocol.server_id

        # 发送消息给 handler，what = 2, arg1 = ack
        msg = Message(what=2, arg1=ack)
        handler.send(msg)

    def handle_device_status(self, protocol):
        DeviceStatusLanProtocol().update_device_status(protocol)
        # LogUtils.d(f"{protocol.request_data_body}")

    def handle_config_query_response(self, protocol: BaseLanProtocol) -> None:
        """处理配置查询响应（异步版本）"""
        # 检查下载状态
        # if DownloadModel.get_instance().is_downloading:
        #     _LOGGER.debug("Download in progress, skipping response handling")
        #     return
    
        # frame_id = int(protocol..get("frame_id", 0))
        # if frame_id < FrameIdSingleton.get_instance().frame_id:
        #     return
    
        try:
            config_ack = json.loads(protocol.request_data_body)
        except json.JSONDecodeError:
            LogUtils.e("Invalid JSON payload")
            return
    
        LogUtils.d(f"Config mode ack value: {json.dumps(config_ack)}")
    
        # 处理认证错误场景
        # if config_ack.get("ack") == 0 and config_ack.get("msg") in ["WRONG_T1", "T1_EXPIRED"]:
        #     await self._handle_authentication_error(config_ack)
        #     return
    
        self.is_expired = False
    
        if config_ack.get("ack") != 1:
            return
        self._handle_sync_complete(config_ack)
        # 处理配置同步完成
        if config_ack.get("T1") == config_ack.get("T2"):
            self._handle_sync_complete(config_ack)
            return
    
        # 处理增量更新
        self._handle_partial_update(config_ack)

    def get_config_req(self, t1: int, t2: int, mod_info_list: List[ModInfo]):
        if not mod_info_list:
            return

        for mod_info in mod_info_list:
            self.m_change_table_name_list.append(mod_info.tbl)

            if mod_info.del_n > 0:
                req_list = [
                    self.add_req_by_type(t1, t2, mod_info.tbl, "del", mod_info.del_n)
                ]
                self.config_req_table_name_list.append(mod_info.tbl)
                self.m_lan_data_request_model.request_config_fetch_list(req_list)

            if mod_info.ins_n > 0:
                req_list = [
                    self.add_req_by_type(t1, t2, mod_info.tbl, TableOperateType.TYPE_INSERT, mod_info.ins_n)
                ]
                self.config_req_table_name_list.append(mod_info.tbl)
                self.m_lan_data_request_model.request_config_fetch_list(req_list)

            if mod_info.upd_n > 0:
                req_list = [
                    self.add_req_by_type(t1, t2, mod_info.tbl, TableOperateType.TYPE_UPDATE, mod_info.upd_n)
                ]
                self.config_req_table_name_list.append(mod_info.tbl)
                self.m_lan_data_request_model.request_config_fetch_list(req_list)

    # def handle_config_query_response(self, base_lan_protocol):
    #     # if DownLoadModel.get_instance().is_download():
    #     #     LogUtils.d(TAG, "handleConfigQueryResponse() is download db return")
    #     #     return

    #     frame_id = ConvertUtils.to_int(base_lan_protocol.frame_id)
    #     # if frame_id < FrameIdSingleton.get_instance().get_frame_id():
    #     #     return

    #     config_mod_ack = ConfigModAck.from_dict(json.loads(base_lan_protocol.request_data_body))
    #     LogUtils.d(f"config mode ack value: {json.dumps(config_mod_ack.to_dict())}")

    #     self.is_expired = False
    #     if config_mod_ack.ack != 1:
    #         return

    #     if config_mod_ack.T1 == config_mod_ack.T2:
    #         LogUtils.d(LeelenConst.TAG_GATEWAY, "update config complete")
    #         LogUtils.d(LeelenConst.TAG_GATEWAY, "网关数据同步完成update config complete")
    #         # event = FetchConfigCompleteEvent(is_complete=True)

    #         # if self.m_change_table_name_list:
    #         #     event.update_table_list = list(self.m_change_table_name_list)
    #         #
    #         # RxBus.get_instance().post(event)
    #         # self.m_change_table_name_list.clear()

    #         LogUtils.d("Configuration update complete, 开始获取设备状态信息")
    #         devices = asyncio.run(HttpApi.get_instance().query_devices("/Users/snail/Downloads/dump.db"))
    #         for device in devices:
    #             LanDataRequestModel.get_instance().request_device_status(device.get("dev_addr"))

    #     # if DeviceModel.get_instance().get_arm_address() == -1 or ArmDao.get_instance().get_arm_list():
    #     #     return
    #     # GatewayDaoModel.get_instance().delete_current_gateway_data()
    #     # LanDataRequestModel.get_instance().request_config_query()
    #     # return

    #     if not config_mod_ack.mod_info:
    #     #     DownloadDbByHttpSingleton.get_instance().set_can_download_by_http(True)
    #         ConfigDao.get_instance().update_config_time(config_mod_ack.T2, None)

    #     # struct_version = StructVersionDao.get_instance().get_struct_version_by_gateway()
    #     need_sync = False
    #     # if struct_version:
    #     #     i = struct_version.config_struct_version
    #     #     i2 = config_mod_ack.config_struct_version
    #     #     need_sync = (i != i2) and ((i & 0xFFFF) < (i2 & 0xFFFF))

    #     # new_struct = StructVersion()
    #     # new_struct.gateway_address = GatewayInfo.get_instance().gateway_desc_string
    #     # new_struct.config_struct_version = config_mod_ack.config_struct_version
    #     # StructVersionDao.get_instance().save_or_update_struct_version_by_gateway(new_struct)

    #     config_by_gateway = ConfigDao.get_instance().get_config_by_gateway()
    #     T1 = config_mod_ack.T1

    #     if T1 == 0 or (not need_sync and config_by_gateway and
    #                    config_by_gateway.config_version == config_mod_ack.config_version and
    #                    config_by_gateway.latest_time <= config_mod_ack.T2):

    #         # if config_by_gateway and config_by_gateway.latest_time != T1:
    #         #     return
    #         # if T1 == 0:
    #         LogUtils.d(LeelenConst.TAG_GATEWAY, "网关数据 同步2")
    #         # if frame_id < FrameIdSingleton.get_instance().get_frame_id():
    #         #     LogUtils.d("handleConfigQueryResponse() frameId < latestFrameId")
    #         #     return

    #         # SharePreferenceModel.set_config_version(config_mod_ack.config_version)
    #         self.get_config_req(config_mod_ack.T1, config_mod_ack.T2, config_mod_ack.mod_info)
    #         # DownloadDbByHttpSingleton.get_instance().set_can_download_by_http(True)
    #         return

    #     LogUtils.d(LeelenConst.TAG_GATEWAY, "网关数据 同步1")
    #     # if (ConnectLan.get_instance().get_connect_state() == ConnectState.CONNECTED and
    #     #         ConnectLan.get_instance().get_logon_state() == LogonState.LOGGED_ON):
    #     #     DownLoadModel.get_instance().download_gateway_db(True)
    #     # elif DownloadDbByHttpSingleton.get_instance().get_can_download_by_http():
    #     #     DownLoadModel.get_instance().download_gateway_db(False)
    #     # else:
    #     #     GatewayDaoModel.get_instance().delete_current_gateway_data()
    #     #     SharePreferenceModel.set_is_expired(True)
    #     #     LanDataRequestModel.get_instance().request_config_query()

    def _handle_sync_complete(self, config_ack: Dict[str, Any]) -> None:
        """处理完整配置同步(当前仅记录日志)。

        原实现对每个设备调用 asyncio.run(HttpApi.query_devices(...)),且路径硬编码为
        /Users/snail/Downloads/dump.db —— 该路径不存在,且在被调用线程里 asyncio.run 会在事件循环
        线程执行时报 RuntimeError。设备在线状态查询已由接收路径自行轮询,此处在卸载/重载边界保留日志钩子。
        """
        LogUtils.d("Configuration update complete, 开始获取设备状态信息(由设备接收路径自动轮询)")

        # event_data = {
        #     "is_complete": True,
        #     "update_tables": self.change_table_list.copy() if self.change_table_list else None
        # }
        # self.coordinator.hass.bus.async_fire("fetch_config_complete", event_data)
        #
        # self.change_table_list.clear()

        # if DeviceModel.get_instance().arm_address == -1 or not ArmDao.get_instance().get_arm_list():
        #     GatewayDaoModel.get_instance().delete_current_gateway_data()
        # LanDataRequestModel.get_instance().request_config_query()

    def handle_config_fetch_response(self, base_lan_protocol: BaseLanProtocol):
        with self._lock:  # 单例对象上的真实互斥,替代每次新建的假锁
            tag = self.TAG
            LogUtils.d(tag, f"handleConfigFetchResponse() {base_lan_protocol.request_data_body}")

            fetch_config_mod_ack = json.loads(
                base_lan_protocol.request_data_body,
                object_hook=lambda d: FetchConfigModAck(**d)
            )

            if fetch_config_mod_ack:
                LogUtils.d(tag, f"config fetch ack response tbl ： {fetch_config_mod_ack.to_dict()}")
                # LogUtils.d(tag, f"handleConfigFetchResponse() frameId : {i}, latestFrameId : {frame_id}")

                skip_tables = {
                    GatewayTable.DEVICE_STATE_TABLE_NAME.lower(),
                    GatewayTable.LOGIC_SERVER_STATE_TABLE_NAME.lower(),
                    GatewayTable.SENSOR_STATE_TABLE_NAME.lower(),
                }

                # if i < frame_id and fetch_config_mod_ack.tbl.lower() not in skip_tables:
                #     return

                AckToDao.get_instance().transform_data(fetch_config_mod_ack)

                if fetch_config_mod_ack.tbl.lower() not in skip_tables:
                    if fetch_config_mod_ack.tbl in self.config_req_table_name_list:
                        self.config_req_table_name_list.remove(fetch_config_mod_ack.tbl)

                if fetch_config_mod_ack.num_left != 0:
                    self.m_lan_data_request_model.request_config_fetch(
                        self.add_req_by_type(
                            fetch_config_mod_ack.T3,
                            fetch_config_mod_ack.T2,
                            fetch_config_mod_ack.tbl,
                            fetch_config_mod_ack.type,
                            fetch_config_mod_ack.num_left
                        )
                    )
                    if fetch_config_mod_ack.tbl.lower() not in skip_tables:
                        self.config_req_table_name_list.append(fetch_config_mod_ack.tbl)
                elif not self.config_req_table_name_list and fetch_config_mod_ack.tbl.lower() not in skip_tables:
                    LogUtils.d(LeelenConst.TAG_GATEWAY, "configReqTableNameList success")
                    i3 = ConvertUtils.to_int(base_lan_protocol.frame_id)
                    frame_id2 = frame_id_counter.frame_id
                    LogUtils.d(tag, f"handleConfigFetchResponse2() frameId2 : {i3}, latestFrameId2 : {frame_id2}")
                    # if i3 < frame_id2:
                    #     return
                    # config = Config()
                    # config.config_version = SharePreferenceModel.get_config_version()
                    # config.latest_time = fetch_config_mod_ack.T2
                    # config.gateway_address = GatewayInfo.get_instance().gateway_desc_string
                    # ConfigDao.get_instance().save_or_update_config_by_gateway(config)
                    self.m_lan_data_request_model.request_config_query()

    #
    # def handle_config_fetch_response(self, protocol: BaseLanProtocol) -> None:
    #     """处理配置获取响应（异步版本）"""
    #     # with self._lock:  # 保证线程安全
    #     LogUtils.d("处理配置获取响应")
    #
    #     try:
    #         fetch_ack = json.loads(protocol.request_data_body)
    #     except json.JSONDecodeError:
    #         LogUtils.e("无效的JSON数据")
    #         return
    #
    #         # frame_id = int(protocol.get("frame_id", 0))
    #         # latest_frame_id = FrameIdSingleton.get_instance().frame_id
    #
    #     if not fetch_ack:
    #         return
    #
    #     LogUtils.d(f"配置获取响应表{fetch_ack}")
    #     #     # 日志记录
    #     # LogUtils.d(
    #     #     f"配置获取响应表: {fetch_ack['tbl']}, 类型: {fetch_ack['type']}, "
    #     #     f"剩余数量: {fetch_ack['num_left']}, T2: {fetch_ack['T2']}, T3: {fetch_ack['T3']}"
    #     # )

    def _handle_partial_update(self, config_ack: Dict[str, Any]) -> None:
        """处理部分配置更新。

        原实现引用 undefined 的 needs_update / _get_config_request,且在 dataclass Config 上访问
        不存在的 .version 字段,必然崩溃;还调用 update_config_time(T2, None) 多传一个参数。
        此处收敛为「记录同步时刻 + 日志」的兜底实现,避免 LAN 响应处理链中断 —— 待真机验证。
        """
        if not config_ack.get("mod_info"):
            ConfigDao.get_instance().update_config_time(config_ack.get("T2", 0))

        LogUtils.d(
            LeelenConst.TAG_GATEWAY,
            f"config partial update, T1={config_ack.get('T1')}, T2={config_ack.get('T2')}"
        )
        #     if ConnectLan.get_instance().is_connected_and_logged_in:
        #         DownloadModel.get_instance().download_gateway_db(force=True)
        #     elif DownloadDbByHttpSingleton.get_instance().can_download_http:
        #         DownloadModel.get_instance().download_gateway_db(force=False)
        #     else:
        #         GatewayDaoModel.get_instance().delete_current_gateway_data()
        #         SharePreferenceModel.set_is_expired(True)
        #         LanDataRequestModel.get_instance().request_config_query()

    def handle_get_device_status(self, base_lan_protocol: BaseLanProtocol):
        b_arr = base_lan_protocol.request_data_body
        if len(b_arr) != 4:
            return

        first_byte = b_arr[0]
        if first_byte == 0:
            return

        # 提取两个字节作为设备地址（大端序）
        address_bytes = b_arr[1:3]
        unsigned_short = ConvertUtils.to_unsigned_int(address_bytes)
        # unsigned_short = struct.unpack('>H', address_bytes)[0]  # 使用大端序解析

        # 提取状态字节
        status_byte = b_arr[3]

        # 记录日志
        LogUtils.d(f"handleGetDeviceStatus() device address : {unsigned_short} status : {status_byte}")

        # 更新设备状态 记录设备的在线状态 online 与否
        # DeviceStateModel.get_instance().add_or_update_device_state(unsigned_short, status_byte)
        #
        # # 发送事件
        # RxBus.get_instance().post(DeviceStatusUpdateEvent())

    # device_status = DeviceStatusEvent()
    # device_status.logic_address = logic_address
    # device_status.function_id = function_id
    # device_status.state = state_bytes
    # FlowRxBus.get_instance().post(device_status)
    #
    # 原 Java 参考实现(源码原第 399-842 行)已移至 docs/reference/LanDataResponseHandleModel.java.md。
    def handle_config_modify_notify(self, base_lan_protocol: BaseLanProtocol):
        """网关通知「配置已变更」(LAN 协议 771)。

        Java 原实现在「已连接且已登录」分支调用 DownLoadModel.downloadGatewayDb(true)
        从云端重下设备库,否则 deleteCurrentGatewayData + requestConfigQuery。
        本移植不做收包线程里的异步下载(同类坑见 _handle_sync_complete 的注释),
        因此链路可用时改为向网关查询配置并拉一次状态 —— 这是收包线程上唯一能生效的
        动作;云端设备库的重下仍由集成 setup 与「同步设备」承担。
        """
        try:
            data = json.loads(base_lan_protocol.request_data_body)
            config_modify = ConfigModifyInfo.from_dict(data)

            local_config = ConfigDao.get_instance().get_config_by_gateway()

            if local_config is not None and \
               config_modify.config_version == local_config.config_version:

                cloud_time = config_modify.T2
                local_time = local_config.latest_time

                if cloud_time >= local_time:
                    if cloud_time > local_time:
                        self.m_lan_data_request_model.request_config_query()
                    return

            # 延迟导入:ConnectLan 反向依赖本模块(收包分发处调用本方法),模块级导入会成环。
            from ..BaseConnect import ConnectState, LogonState
            from ..HeartbeatService import HeartbeatService

            connect_lan = HeartbeatService.get_instance().connect_lan
            if connect_lan is not None and \
               connect_lan.get_connect_state() == ConnectState.CONNECTED and \
               connect_lan.get_logon_state() == LogonState.LOGGED_ON:
                self.m_lan_data_request_model.request_config_query()
                self.m_lan_data_request_model.get_state_data()
            else:
                # 未登录时 request_config_query 的帧会被 send_data 丢弃,查询留到登录成功后
                # (ConnectLan 的登录成功分支本就会 request_config_query + get_state_data)。
                LogUtils.d(self.TAG, "收到配置变更通知,但链路未就绪,等待登录后的配置查询")

        except Exception as e:
            LogUtils.e(f"handle_config_modify_notify error: {e}")

        # 原 Java 参考实现(源码原第 887-1899 行)已移至 docs/reference/LanDataResponseHandleModel.java.md。
