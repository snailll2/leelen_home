import asyncio
import json
import threading
from typing import Dict, Any, List

from ..common import LeelenConst
from ..common.FrameIdSingleton import FrameIdSingleton
from ..common.LeelenType import GatewayTable, TableOperateType
from ..entity.GatewayInfo import GatewayInfo
from ..entity.ConfigModifyInfo import ConfigModifyInfo
from ..entity.Message import Message
from ..entity.ack.ConfigModAck import ConfigModAck
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


class LanDataResponseHandleModel:
    TAG = "LanDataResponseHandleModel"
    _instance = None  # 用于实现单例

    def __init__(self):
        self.config_req_table_name_list = []
        self.m_change_table_name_list = []
        self.is_expired = False
        self.m_lan_data_request_model = LanDataRequestModel.get_instance()

    @staticmethod
    def get_instance():
        if LanDataResponseHandleModel._instance is None:
            LanDataResponseHandleModel._instance = LanDataResponseHandleModel()
        return LanDataResponseHandleModel._instance

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

        GatewayInfo.get_instance().set_tcp_server_code(protocol.server_id)

        # 发送消息给 handler，what = 2, arg1 = ack
        msg = Message(what=2, arg1=ack)
        handler.send(msg)

    def handle_device_status(self, protocol):
        DeviceStatusLanProtocol.get_instance().update_device_status(protocol)
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
    #     # new_struct.gateway_address = GatewayInfo.get_instance().get_gateway_desc_string()
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
        """处理完整配置同步"""
        from ... import HttpApi

        LogUtils.d("Configuration update complete, 开始获取设备状态信息")
        devices = asyncio.run(HttpApi.get_instance().query_devices("dump.db"))
        for device in devices:
            LanDataRequestModel.get_instance().request_device_status(device.get("dev_addr"))

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
        with threading.Lock():  # 模拟 synchronized(this)
            tag = self.TAG
            LogUtils.d(tag, f"handleConfigFetchResponse() {base_lan_protocol.request_data_body}")

            fetch_config_mod_ack = json.loads(
                base_lan_protocol.request_data_body,
                object_hook=lambda d: FetchConfigModAck(**d)
            )

            i = ConvertUtils.to_int(base_lan_protocol.frame_id)
            frame_id = FrameIdSingleton.get_instance().get_frame_id()

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
                    frame_id2 = FrameIdSingleton.get_instance().get_frame_id()
                    LogUtils.d(tag, f"handleConfigFetchResponse2() frameId2 : {i3}, latestFrameId2 : {frame_id2}")
                    # if i3 < frame_id2:
                    #     return
                    # config = Config()
                    # config.config_version = SharePreferenceModel.get_config_version()
                    # config.latest_time = fetch_config_mod_ack.T2
                    # config.gateway_address = GatewayInfo.get_instance().get_gateway_desc_string()
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
        """处理部分配置更新"""
        if not config_ack.get("mod_info"):
        #     DownloadDbByHttpSingleton.get_instance().can_download_http = True
            ConfigDao.get_instance().update_config_time(config_ack["T2"], None)

        # struct_version = StructVersionDao.get_instance().get_struct_version()
        # needs_update = (
        #         struct_version is None or
        #         (struct_version.config_struct_version & 0xFFFF) < (config_ack["config_struct_version"] & 0xFFFF)
        # )

        # new_version = StructVersion(
        #     gateway_address=GatewayInfo.get_instance().gateway_desc,
        #     config_struct_version=config_ack["config_struct_version"]
        # )
        # StructVersionDao.get_instance().save_version(new_version)

        current_config = ConfigDao.get_instance().get_current_config()
        if (
                config_ack["T1"] == 0 or
                (not needs_update and
                 current_config and
                 current_config.version == config_ack["config_version"] and
                 current_config.latest_time <= config_ack["T2"])
        ):
            if current_config and current_config.latest_time != config_ack["T1"]:
                return
        #
            LogUtils.d(LeelenConst.TAG_GATEWAY, "Secondary gateway data sync")
        #     SharePreferenceModel.set_config_version(config_ack["config_version"])
            self._get_config_request(config_ack["T1"], config_ack["T2"], config_ack["mod_info"])
        #     DownloadDbByHttpSingleton.get_instance().can_download_http = True
        else:
            LogUtils.d(LeelenConst.TAG_GATEWAY, "Primary gateway data sync")
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
    # public class LanDataResponseHandleModel {
    #     private static final String TAG = "LanDataResponseHandleModel";
    #     private List<String> configReqTableNameList;
    #     private boolean isExpired;
    #     private List<String> mChangeTableNameList;
    #     private LanDataRequestModel mLanDataRequestModel;
    #
    #     private LanDataResponseHandleModel() {
    #         this.configReqTableNameList = new ArrayList();
    #         this.mChangeTableNameList = new ArrayList();
    #         this.isExpired = false;
    #         this.mLanDataRequestModel = LanDataRequestModel.getInstance();
    #     }
    #
    #     private FetchConfigModReq addReqByType(long var1, long var3, String var5, String var6, int var7) {
    #         FetchConfigModReq var8 = new FetchConfigModReq();
    #         var8.T1 = var1;
    #         var8.T2 = var3;
    #         var8.tbl = var5;
    #         var8.type = var6;
    #         if (var7 < 100) {
    #             var8.num = var7;
    #         } else {
    #             var8.num = 100;
    #         }
    #
    #         return var8;
    #     }
    #
    #     private void getConfigReq(long var1, long var3, List<ModInfo> var5) {
    #         ArrayList var6 = new ArrayList();
    #         if (!CollectionUtils.isEmpty(var5)) {
    #             Iterator var8 = var5.iterator();
    #
    #             while (var8.hasNext()) {
    #                 ModInfo var7 = (ModInfo) var8.next();
    #                 this.mChangeTableNameList.add(var7.tbl);
    #                 if (var7.del_n > 0) {
    #                     var6.clear();
    #                     var6.add(this.addReqByType(var1, var3, var7.tbl, "del", var7.del_n));
    #                     this.configReqTableNameList.add(var7.tbl);
    #                     this.mLanDataRequestModel.requestConfigFetch(var6);
    #                 }
    #
    #                 if (var7.ins_n > 0) {
    #                     var6.clear();
    #                     var6.add(this.addReqByType(var1, var3, var7.tbl, "ins", var7.ins_n));
    #                     this.configReqTableNameList.add(var7.tbl);
    #                     this.mLanDataRequestModel.requestConfigFetch(var6);
    #                 }
    #
    #                 if (var7.upd_n > 0) {
    #                     var6.clear();
    #                     var6.add(this.addReqByType(var1, var3, var7.tbl, "upd", var7.upd_n));
    #                     this.configReqTableNameList.add(var7.tbl);
    #                     this.mLanDataRequestModel.requestConfigFetch(var6);
    #                 }
    #             }
    #
    #         }
    #     }
    #
    #     public static LanDataResponseHandleModel getInstance() {
    #         return LanDataResponseHandleModel.SingletonInstance.INSTANCE;
    #     }
    #
    #     public void clearReqTable() {
    #         LogUtils.d(TAG, "clearReqTable()");
    #         this.configReqTableNameList.clear();
    #     }
    #
    #     public void handleAddHopeBgmDeviceResponse(BaseLanProtocol var1) {
    #         BaseAck var3 = (BaseAck) JSON.parseObject(var1.requestDataBody, BaseAck.class);
    #         AddHopeBgmDeviceResponseEvent var2 = new AddHopeBgmDeviceResponseEvent();
    #         var2.code = var3.ack;
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleAddService(BaseLanProtocol var1) {
    #         BaseAck var2 = (BaseAck) JSON.parseObject(var1.requestDataBody, BaseAck.class);
    #         AddServiceResponseEvent var3 = new AddServiceResponseEvent();
    #         var3.ack = var2.ack;
    #         var3.frameId = ConvertUtils.toInt(var1.frameId);
    # //        com.leelen.core.utils.RxBus.getInstance().post(var3);
    #     }
    #
    #     public void handleAddServiceResult(BaseLanProtocol var1) {
    #         AddServiceResult var2 = (AddServiceResult) JSON.parseObject(var1.requestDataBody, AddServiceResult.class);
    #         String var4 = TAG;
    #         StringBuilder var3 = new StringBuilder();
    #         var3.append("handleAddServiceResult() result : ");
    #         var3.append(JSON.toJSONString(var2));
    #         LogUtils.d(var4, var3.toString());
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleAddTemporaryPasswordResponse(BaseLanProtocol var1) {
    #         AddTemporaryPasswordAck var2 = (AddTemporaryPasswordAck) JSON.parseObject(var1.requestDataBody, AddTemporaryPasswordAck.class);
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleAppDevicePassThroughResponse(BaseLanProtocol var1) {
    #         byte[] var2 = var1.requestDataBody;
    #         AppDevicePassThroughEvent var3 = new AppDevicePassThroughEvent();
    #         var3.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         String var4 = TAG;
    #         StringBuilder var5 = new StringBuilder();
    #         var5.append("handleAppDevicePassThroughResponse() body : ");
    #         var5.append(com.leelen.sdk.core.utils.ConvertUtils.bytesToHex(var2));
    #         LogUtils.d(var4, var5.toString());
    #         ByteBuffer var7 = ByteBuffer.wrap(var2);
    #         byte[] var9 = new byte[1];
    #         byte[] var8 = new byte[1];
    #         var7.get(var9);
    #         byte var6 = var9[0];
    #         var3.ack = var6;
    #         if (var6 == 1) {
    #             var7.get(var8);
    #             var6 = var8[0];
    #             var8 = new byte[var6];
    #             var7.get(var8);
    #             var3.dataLen = var6;
    #             var3.data = var8;
    #         }
    #
    #         var3.logicAddress = com.leelen.sdk.core.utils.ConvertUtils.toUnsignedShort(var1.deviceSource);
    #         RxBus.getInstance().post(var3);
    #     }
    #
    #     public void handleBgmPassThroughData(BaseLanProtocol var1) {
    #         byte[] var2 = var1.deviceSource;
    #         BgmPassThroughReply var3 = (BgmPassThroughReply) JSON.parseObject(var1.requestDataBody, BgmPassThroughReply.class);
    #         BgmPassThroughReplyEvent var4 = (BgmPassThroughReplyEvent) (new WeakReference(new BgmPassThroughReplyEvent())).get();
    #         var4.ack = var3.ack;
    #         if (var2.length == 2) {
    #             int var5 = ConvertUtils.toUnsignedShort(var2);
    #             if (var5 < 0) {
    #                 var4.address = var5 + 65536;
    #             } else {
    #                 var4.address = var5;
    #             }
    #         }
    #
    #         if (var4.ack == 1) {
    #             try {
    #                 byte[] var10 = Base64Utils.decode(var3.data);
    #                 if (var10.length > 4) {
    #                     byte[] var9 = new byte[4];
    #                     var2 = new byte[var10.length - 4];
    #                     ByteBuffer var11 = ByteBuffer.wrap(var10);
    #                     var11.get(var9);
    #                     var11.get(var2);
    #                     var4.data = (BgMusicBase) JSON.parseObject(var2, BgMusicBase.class);
    #                     LogUtils.d(TAG, "handleBgmPassThroughData() reply data");
    #                 }
    #             } catch (Exception var7) {
    #                 String var8 = TAG;
    #                 StringBuilder var6 = new StringBuilder();
    #                 var6.append("handleBgmPassThroughData() exception : ");
    #                 var6.append(var7.toString());
    #                 LogUtils.e(var8, var6.toString());
    #             }
    #         }
    #
    #         var4.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         RxBus.getInstance().post(var4);
    #     }
    #
    #     public void handleBindLanResponse(BaseLanProtocol var1) {
    #         byte[] var5 = var1.requestDataBody;
    #         boolean var2 = false;
    #         BindGatewayAck var6 = (BindGatewayAck) JSON.parseObject(var5, BindGatewayAck.class);
    #         String var3 = TAG;
    #         StringBuilder var4 = new StringBuilder();
    #         var4.append("bind gateway ack : ");
    #         var4.append(var6.ack);
    #         var4.append(" account :");
    #         var4.append(var6.account);
    #         var4.append("gateway id: ");
    #         var4.append(var6.gatewayID);
    #         LogUtils.d(var3, var4.toString());
    #         if (var6.ack == 1) {
    #             GatewayInfo var7 = GatewayInfo.getInstance();
    #             var7.setGatewayDesc(var7.getTempGatewayDesc());
    #             var7.setHadBind(true);
    #         }
    #
    #         BindLanResultEvent var8 = new BindLanResultEvent();
    #         if (var6.ack == 1) {
    #             var2 = true;
    #         }
    #
    #         var8.bindSuc = var2;
    #         RxBus.getInstance().post(var8);
    #     }
    #
    #     public void handleBindXiaoBai(BaseLanProtocol var1) {
    #         BindRobotAck var2 = (BindRobotAck) JSON.parseObject(var1.requestDataBody, BindRobotAck.class);
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleCancelGatewayDevice(BaseLanProtocol var1) {
    #         BaseAck var2 = (BaseAck) JSON.parseObject(var1.requestDataBody, BaseAck.class);
    #         String var3 = TAG;
    #         StringBuilder var4 = new StringBuilder();
    #         var4.append("gateway invite response state value :");
    #         var4.append(var2.ack);
    #         LogUtils.d(var3, var4.toString());
    #         DeleteAveGatewayEvent var5 = new DeleteAveGatewayEvent();
    #         var5.cancelFrameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         var5.code = var2.ack;
    #         RxBus.getInstance().post(var5);
    #     }
    #
    #     public void handleCommonCommitConfig(BaseLanProtocol var1) {
    #         CommonCommitConfigAck var2 = (CommonCommitConfigAck) JSON.parseObject(var1.requestDataBody, CommonCommitConfigAck.class);
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleConfigFetchResponse(BaseLanProtocol var1) {
    #         synchronized (this) {
    #         }
    #
    #         Throwable var10000;
    #         label1075:
    #         {
    #             String var2;
    #             FetchConfigModAck var3;
    #             int var4;
    #             int var5;
    #             boolean var10001;
    #             try {
    #                 var2 = TAG;
    #                 LogUtils.d(var2, "handleConfigFetchResponse()");
    #                 var3 = (FetchConfigModAck) JSON.parseObject(var1.requestDataBody, FetchConfigModAck.class);
    #                 LogUtils.d(var2, JSON.toJSONString(var1));
    #
    #                 var4 = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #                 var5 = FrameIdSingleton.getInstance().getFrameId();
    #             } catch (Throwable var99) {
    #                 var10000 = var99;
    #                 var10001 = false;
    #                 break label1075;
    #             }
    #
    #             if (var3 != null) {
    #                 try {
    #                     StringBuilder var6 = new StringBuilder();
    #                     var6.append("config fetch ack response tbl ： ");
    #                     var6.append(var3.tbl);
    #                     var6.append(", type :");
    #                     var6.append(var3.type);
    #                     var6.append(", left_num:");
    #                     var6.append(var3.num_left);
    #                     var6.append(", t2 : ");
    #                     var6.append(var3.T2);
    #                     LogUtils.d(var2, var6.toString());
    #                     var6 = new StringBuilder();
    #                     var6.append("config fetch ack response tbl ： ");
    #                     var6.append(var3.tbl);
    #                     var6.append(", type :");
    #                     var6.append(var3.type);
    #                     var6.append(", left_num:");
    #                     var6.append(var3.num_left);
    #                     var6.append(", t2 : ");
    #                     var6.append(var3.T2);
    #                     var6.append(", t3 : ");
    #                     var6.append(var3.T3);
    #                     LogUtils.d("TAG_GATEWAY", var6.toString());
    #                     var6 = new StringBuilder();
    #                     var6.append("handleConfigFetchResponse() frameId : ");
    #                     var6.append(var4);
    #                     var6.append(", latestFrameId : ");
    #                     var6.append(var5);
    #                     LogUtils.d(var2, var6.toString());
    #                 } catch (Throwable var95) {
    #                     var10000 = var95;
    #                     var10001 = false;
    #                     break label1075;
    #                 }
    #
    #                 if (var4 < var5) {
    #                     label1082:
    #                     {
    #                         boolean var7;
    #                         try {
    #                             if ("dev_state_tbl".equalsIgnoreCase(var3.tbl) || "logic_srv_state_tbl".equalsIgnoreCase(var3.tbl)) {
    #                                 break label1082;
    #                             }
    #
    #                             var7 = "sensor_active_state_tbl".equalsIgnoreCase(var3.tbl);
    #                         } catch (Throwable var98) {
    #                             var10000 = var98;
    #                             var10001 = false;
    #                             break label1075;
    #                         }
    #
    #                         if (!var7) {
    #                             return;
    #                         }
    #                     }
    #                 }
    #
    #                 int var8;
    #                 label1054:
    #                 {
    #                     try {
    #                         AckToDao.getInstance().transformData(var3);
    #                         if ("dev_state_tbl".equalsIgnoreCase(var3.tbl) || "logic_srv_state_tbl".equalsIgnoreCase(var3.tbl) || "sensor_active_state_tbl".equalsIgnoreCase(var3.tbl)) {
    #                             break label1054;
    #                         }
    #
    #                         var8 = this.configReqTableNameList.indexOf(var3.tbl);
    #                     } catch (Throwable var97) {
    #                         var10000 = var97;
    #                         var10001 = false;
    #                         break label1075;
    #                     }
    #
    #                     if (var8 != -1) {
    #                         try {
    #                             this.configReqTableNameList.remove(var8);
    #                         } catch (Throwable var94) {
    #                             var10000 = var94;
    #                             var10001 = false;
    #                             break label1075;
    #                         }
    #                     }
    #                 }
    #
    #                 try {
    #                     var8 = var3.num_left;
    #                 } catch (Throwable var93) {
    #                     var10000 = var93;
    #                     var10001 = false;
    #                     break label1075;
    #                 }
    #
    #                 if (var8 != 0) {
    #                     try {
    #                         FetchConfigModReq var100 = this.addReqByType(var3.T3, var3.T2, var3.tbl, var3.type, var8);
    #                         this.mLanDataRequestModel.requestConfigFetch(var100);
    #                         if (!"dev_state_tbl".equalsIgnoreCase(var3.tbl) && !"logic_srv_state_tbl".equalsIgnoreCase(var3.tbl) && !"sensor_active_state_tbl".equalsIgnoreCase(var3.tbl)) {
    #                             this.configReqTableNameList.add(var3.tbl);
    #                         }
    #                     } catch (Throwable var91) {
    #                         var10000 = var91;
    #                         var10001 = false;
    #                         break label1075;
    #                     }
    #                 } else {
    #                     int var9;
    #                     try {
    #                         if (this.configReqTableNameList.size() != 0 || "dev_state_tbl".equalsIgnoreCase(var3.tbl) || "logic_srv_state_tbl".equalsIgnoreCase(var3.tbl) || "sensor_active_state_tbl".equalsIgnoreCase(var3.tbl)) {
    #                             return;
    #                         }
    #
    #                         LogUtils.d("TAG_GATEWAY", "configReqTableNameList success");
    #                         var8 = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #                         var9 = FrameIdSingleton.getInstance().getFrameId();
    #                         StringBuilder var101 = new StringBuilder();
    #                         var101.append("handleConfigFetchResponse2() frameId2 : ");
    #                         var101.append(var4);
    #                         var101.append(", latestFrameId2 : ");
    #                         var101.append(var5);
    #                         LogUtils.d(var2, var101.toString());
    #                     } catch (Throwable var96) {
    #                         var10000 = var96;
    #                         var10001 = false;
    #                         break label1075;
    #                     }
    #
    #                     if (var8 < var9) {
    #                         return;
    #                     }
    #
    #                     try {
    #                         Config var103 = new Config();
    #                         var103.config_version = SharePreferenceModel.getConfigVersion();
    #                         var103.latest_time = var3.T2;
    #                         var103.gateway_address = GatewayInfo.getInstance().getGatewayDescString();
    #                         ConfigDao.getInstance().saveOrUpdateConfigByGateWay(var103);
    #                         this.mLanDataRequestModel.requestConfigQuery();
    #                     } catch (Throwable var92) {
    #                         var10000 = var92;
    #                         var10001 = false;
    #                         break label1075;
    #                     }
    #                 }
    #             }
    #
    #             return;
    #         }
    #
    # //        Throwable var102 = var10000;
    # //        throw var102;
    #     }
    #
    #     public void handleConfigFileImport(BaseLanProtocol var1) {
    #         BaseAck var2 = (BaseAck) JSON.parseObject(var1.requestDataBody, BaseAck.class);
    #         String var3 = TAG;
    #         StringBuilder var4 = new StringBuilder();
    #         var4.append("handleConfigFileImport() ack value : ");
    #         var4.append(var2.ack);
    #         LogUtils.d(var3, var4.toString());
    #         ConfigStructVersionEvent var5 = new ConfigStructVersionEvent();
    #         var5.ack = var2.ack;
    #         var5.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         RxBus.getInstance().post(var5);
    #     }
    #
    #     public void handleConfigImportResultNotify(BaseLanProtocol var1) {
    #         ConfigImportResultLanProtocol var2 = new ConfigImportResultLanProtocol();
    #         var2.setFrameId(var1.frameId);
    #         byte[] var4 = var2.getRequestData(com.leelen.sdk.core.utils.ConvertUtils.getLongAddressByType(DeviceType.APP, User.getInstance().getAccountId()), GatewayInfo.getInstance().getGatewayDesc(), (byte[]) null);
    #         LogUtils.d(TAG, "handleConfigImportResultNotify send result data");
    #         ConnectLan.getInstance().sendData(var4);
    #         BaseAck var3 = (BaseAck) JSON.parseObject(var1.requestDataBody, BaseAck.class);
    #         ConfigImportNotifyEvent var5 = new ConfigImportNotifyEvent();
    #         var5.ack = var3.ack;
    #         RxBus.getInstance().post(var5);
    #     }
    #
    #     public void handleConfigLock(BaseLanProtocol var1) {
    #         ConfigLockAck var2 = (ConfigLockAck) JSON.parseObject(var1.requestDataBody, ConfigLockAck.class);
    #         ConfigLockResultEvent var3 = new ConfigLockResultEvent();
    #         var3.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         if (var2.ack == 1) {
    #             var3.isSuc = true;
    #             String var4 = TAG;
    #             StringBuilder var5 = new StringBuilder();
    #             var5.append("handleConfigLock lock success id : ");
    #             var5.append(var2.lock_id);
    #             LogUtils.d(var4, var5.toString());
    #             LockHandleSingleton.getInstance().setLockId(var2.lock_id);
    #         } else if ("locked".equalsIgnoreCase(var2.msg) && var2.op == 0) {
    #             var3.isLockedGw = true;
    #         } else if ("sync".equalsIgnoreCase(var2.msg)) {
    #             var3.isNeedSync = true;
    #         }
    #
    #         RxBus.getInstance().post(var3);
    #     }
    #
    def handle_config_modify_notify(self, base_lan_protocol: BaseLanProtocol):
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

            connect_lan = ConnectLan.get_instance()
            if connect_lan.get_connect_state() == ConnectState.Connected and \
               connect_lan.get_logon_state() == LogonState.LoggedOn:
                pass
                # await DownLoadModel.get_instance().download_gateway_db(force=True)
            else:
                # GatewayDaoModel.get_instance().delete_current_gateway_data()
                self.m_lan_data_request_model.request_config_query()

            self.m_lan_data_request_model.get_state_data()

        except Exception as e:
            LogUtils.e("handle_config_modify_notify error: %s", e)

        # public void handleConfigModifyNotify(BaseLanProtocol var1) {
        #     ConfigModifyInfo var2 = (ConfigModifyInfo) JSON.parseObject(var1.requestDataBody, ConfigModifyInfo.class);
        #     Config var7 = ConfigDao.getInstance().getConfigByGateway();
        #     if (var7 != null && var2.config_version == var7.config_version) {
        #         long var3 = var2.T2;
        #         long var5 = var7.latest_time;
        #         if (var3 >= var5) {
        #             if (var3 > var5) {
        #                 this.mLanDataRequestModel.requestConfigQuery();
        #             }
    
        #             return;
        #         }
        #     }
    
        #     if (ConnectLan.getInstance().getConnectState() == ConnectState.Connected && ConnectLan.getInstance().getLogonState() == LogonState.LoggedOn) {
        #         DownLoadModel.getInstance().downloadGatewayDb(true);
        #     } else {
        #         GatewayDaoModel.getInstance().deleteCurrentGatewayData();
        #         this.mLanDataRequestModel.requestConfigQuery();
        #     }
    
        #     this.mLanDataRequestModel.getStateData();
        # }
    #
    #     public void handleConfigQueryResponse(BaseLanProtocol var1) {
    # //        if (DownLoadModel.getInstance().isDownload()) {
    # //            LogUtils.d(TAG, "handleConfigQueryResponse() is download db return");
    # //        } else {
    #             int var2 = ConvertUtils.toInt(var1.frameId);
    # //            if (var2 >= FrameIdSingleton.getInstance().getFrameId()) {
    #                 ConfigModAck var9 = (ConfigModAck) JSON.parseObject(var1.requestDataBody, ConfigModAck.class);
    #                 String var3 = TAG;
    #                 StringBuilder var4 = new StringBuilder();
    #                 var4.append("config mode ack value ： ");
    #                 var4.append(JSON.toJSONString(var9));
    #                 LogUtils.d(var3, var4.toString());
    #                 var4 = new StringBuilder();
    #                 var4.append("config mode ack value ： ");
    #                 var4.append(JSON.toJSONString(var9));
    #                 LogUtils.d("TAG_GATEWAY", var4.toString());
    #                 boolean var5;
    #                 if (var9.ack != 0 || !"wrong t1".equalsIgnoreCase(var9.msg) && !"t1 expired".equalsIgnoreCase(var9.msg)) {
    #                     var5 = false;
    #                 } else {
    #                     var5 = true;
    #                 }
    #
    #                 if (var5) {
    #                     GatewayDaoModel.getInstance().deleteStateData();
    #                     if (ConnectLan.getInstance().getConnectState() == ConnectState.Connected && ConnectLan.getInstance().getLogonState() == LogonState.LoggedOn) {
    #                         DownLoadModel.getInstance().downloadGatewayDb(true);
    #                         this.isExpired = false;
    #                     } else if (!"t1 expired".equalsIgnoreCase(var9.msg) && !"wrong t1".equalsIgnoreCase(var9.msg)) {
    #                         this.isExpired = false;
    #                         DownLoadModel.getInstance().downloadGatewayDb(false);
    #                     } else {
    #                         LogUtils.i("TAG_GATEWAY", "数据过期或者错误");
    #                         if (!this.isExpired && DownloadDbByHttpSingleton.getInstance().getCanDownloadByHttp()) {
    #                             this.isExpired = true;
    #                             DownLoadModel.getInstance().downloadGatewayDb(false);
    #                         } else {
    #                             GatewayDaoModel.getInstance().deleteCurrentGatewayData();
    #                             SharePreferenceModel.setIsExpired(Boolean.TRUE);
    #                             this.mLanDataRequestModel.requestConfigQuery();
    #                         }
    #                     }
    #
    #                 } else {
    #                     this.isExpired = false;
    #                     if (var9.ack == 1) {
    #                         if (var9.T1 == var9.T2) {
    #                             LogUtils.d(var3, "update config complete");
    #                             LogUtils.d("TAG_GATEWAY", "网关数据同步完成update config complete");
    #                             FetchConfigCompleteEvent var10 = new FetchConfigCompleteEvent();
    #                             var10.isComplete = true;
    #                             if (!CollectionUtils.isEmpty(this.mChangeTableNameList)) {
    #                                 var10.updateTableList = new ArrayList(this.mChangeTableNameList);
    #                             }
    #
    #                             RxBus.getInstance().post(var10);
    #                             this.mChangeTableNameList.clear();
    #                             if (DeviceModel.getInstance().getArmAddress() != -1 && CollectionUtils.isEmpty(ArmDao.getInstance().getArmList())) {
    #                                 GatewayDaoModel.getInstance().deleteCurrentGatewayData();
    #                                 LanDataRequestModel.getInstance().requestConfigQuery();
    #                             }
    #
    #                         } else {
    #                             if (CollectionUtils.isEmpty(var9.mod_info)) {
    #                                 DownloadDbByHttpSingleton.getInstance().setCanDownloadByHttp(true);
    # //                                ConfigDao.getInstance().updateConfigTime(var9.T2, null);
    #                             }
    #
    #                             StructVersion var11;
    #                             label107:
    #                             {
    #                                 var11 = StructVersionDao.getInstance().getStructVersionByGateway();
    #                                 if (var11 != null) {
    #                                     int var6 = var11.config_struct_version;
    #                                     int var13 = var9.config_struct_version;
    #                                     if (var6 != var13 && (var6 & '\uffff') < (var13 & '\uffff')) {
    #                                         var5 = true;
    #                                         break label107;
    #                                     }
    #                                 }
    #
    #                                 var5 = false;
    #                             }
    #
    #                             var11 = new StructVersion();
    #                             var11.gateway_address = GatewayInfo.getInstance().getGatewayDescString();
    #                             var11.config_struct_version = var9.config_struct_version;
    #                             StructVersionDao.getInstance().saveOrUpdateStructVersionByGateWay(var11);
    #                             Config var12 = ConfigDao.getInstance().getConfigByGateway();
    #                             long var7 = var9.T1;
    #                             if (var7 != 0L && (var5 || var12 == null || var12.config_version != var9.config_version || var12.latest_time > var9.T2)) {
    #                                 LogUtils.d("TAG_GATEWAY", "网关数据 同步1");
    #                                 if (ConnectLan.getInstance().getConnectState() == ConnectState.Connected && ConnectLan.getInstance().getLogonState() == LogonState.LoggedOn) {
    #                                     DownLoadModel.getInstance().downloadGatewayDb(true);
    #                                 } else if (DownloadDbByHttpSingleton.getInstance().getCanDownloadByHttp()) {
    #                                     DownLoadModel.getInstance().downloadGatewayDb(false);
    #                                 } else {
    #                                     GatewayDaoModel.getInstance().deleteCurrentGatewayData();
    #                                     SharePreferenceModel.setIsExpired(Boolean.TRUE);
    #                                     LanDataRequestModel.getInstance().requestConfigQuery();
    #                                 }
    #                             } else if (var12 == null || var12.latest_time == var7) {
    #                                 LogUtils.d("TAG_GATEWAY", "网关数据 同步2");
    #                                 if (var2 < FrameIdSingleton.getInstance().getFrameId()) {
    #                                     LogUtils.d(var3, "handleConfigQueryResponse() frameId < latestFrameId");
    #                                     return;
    #                                 }
    #
    #                                 SharePreferenceModel.setConfigVersion(var9.config_version);
    #                                 this.getConfigReq(var9.T1, var9.T2, var9.mod_info);
    #                                 DownloadDbByHttpSingleton.getInstance().setCanDownloadByHttp(true);
    #                             }
    #
    #                         }
    #                     }
    #                 }
    # //            }
    # //        }
    #     }
    #
    #     public void handleConfigWifi(BaseWireLessLanProtocol var1) {
    #         byte[] var4 = var1.requestDataBody;
    #         boolean var2 = false;
    #         BaseAck var3 = (BaseAck) JSON.parseObject(var4, BaseAck.class);
    #         ConfigWifiAckEvent var5 = new ConfigWifiAckEvent();
    #         if (var3.ack == 1) {
    #             var2 = true;
    #         }
    #
    #         var5.success = var2;
    #         RxBus.getInstance().post(var5);
    #     }
    #
    #     public void handleControlDevice(BaseLanProtocol var1) {
    #         byte[] var2 = var1.requestDataBody;
    #         int var3 = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         int var4 = var2.length;
    #         boolean var5 = true;
    #         if (var4 == 1) {
    #             byte var9 = var2[0];
    #             String var6 = TAG;
    #             StringBuilder var8 = new StringBuilder();
    #             var8.append("device control ex response state value :");
    #             var8.append(var9);
    #             LogUtils.d(var6, var8.toString());
    #             DeviceControlAckEvent var7 = new DeviceControlAckEvent();
    #             var7.frameId = var3;
    #             if (var9 != 1) {
    #                 var5 = false;
    #             }
    #
    #             var7.isControlSuc = var5;
    #             var7.code = var9;
    #             RxBus.getInstance().post(var7);
    #         }
    #
    #     }
    #
    #     public void handleControlScene(BaseLanProtocol var1) {
    #         byte[] var2 = var1.requestDataBody;
    #         int var3 = var2.length;
    #         boolean var4 = true;
    #         if (var3 == 1) {
    #             byte var8 = var2[0];
    #             String var5 = TAG;
    #             StringBuilder var6 = new StringBuilder();
    #             var6.append("device control response state value :");
    #             var6.append(var8);
    #             LogUtils.d(var5, var6.toString());
    #             SceneControlAckEvent var7 = new SceneControlAckEvent();
    #             var7.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #             if (var8 != 1) {
    #                 var4 = false;
    #             }
    #
    #             var7.isControlSuc = var4;
    #             FlowRxBus.getInstance().post(var7);
    #         }
    #
    #     }
    #
    #     public void handleCreateArm(BaseLanProtocol var1) {
    #         CreateArmAck var2 = (CreateArmAck) JSON.parseObject(var1.requestDataBody, CreateArmAck.class);
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleCreateFloor(BaseLanProtocol var1) {
    #         ConfigCreateFloorAck var2 = (ConfigCreateFloorAck) JSON.parseObject(var1.requestDataBody, ConfigCreateFloorAck.class);
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleCreateIrKey(BaseLanProtocol var1) {
    #         byte[] var2 = var1.requestDataBody;
    #         String var3 = TAG;
    #         StringBuilder var4 = new StringBuilder();
    #         var4.append("handleCreateIrKey ack:");
    #         boolean var5 = false;
    #         var4.append(var2[0]);
    #         LogUtils.d(var3, var4.toString());
    #         this.mLanDataRequestModel.requestConfigUnlock();
    #         AddIrKeyEvent var6 = new AddIrKeyEvent();
    #         var6.addFrameId = ConvertUtils.toInt(var1.frameId);
    #         if (var2[0] == 1) {
    #             var5 = true;
    #         }
    #
    #         var6.isSuccess = var5;
    #         RxBus.getInstance().post(var6);
    #     }
    #
    #     public void handleCreateLinkage(BaseLanProtocol var1) {
    #         ConfigCreateLinkageAck var2 = (ConfigCreateLinkageAck) JSON.parseObject(var1.requestDataBody, ConfigCreateLinkageAck.class);
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleCreateOrDeleteIrDevice(BaseLanProtocol var1, boolean var2) {
    #         IrDeviceCreateOrDeleteEvent var3 = new IrDeviceCreateOrDeleteEvent();
    #         byte[] var4 = var1.requestDataBody;
    #         boolean var5 = false;
    #         byte var6 = var4[0];
    #         var3.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         var3.isCreate = var2;
    #         if (var6 == 1) {
    #             var5 = true;
    #         }
    #
    #         var3.isSuc = var5;
    #         var3.state = var6;
    #         if (var2) {
    #             byte[] var7 = new byte[1];
    #             byte[] var8 = new byte[2];
    #             byte[] var9 = new byte[2];
    #             ByteBuffer var10 = ByteBuffer.wrap(var4);
    #             var10.get(var7);
    #             var10.get(var8);
    #             var10.get(var9);
    #             var3.createAddress = com.leelen.sdk.core.utils.ConvertUtils.toUnsignedShort(var9);
    #         }
    #
    #         RxBus.getInstance().post(var3);
    #     }
    #
    #     public void handleCreateRoom(BaseLanProtocol var1) {
    #         ConfigCreateRoomAck var2 = (ConfigCreateRoomAck) JSON.parseObject(var1.requestDataBody, ConfigCreateRoomAck.class);
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleCreateScene(BaseLanProtocol var1) {
    #         ConfigCreateSceneAck var2 = (ConfigCreateSceneAck) JSON.parseObject(var1.requestDataBody, ConfigCreateSceneAck.class);
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleCreateTimer(BaseLanProtocol var1) {
    #         ConfigCreateTimingAck var2 = (ConfigCreateTimingAck) JSON.parseObject(var1.requestDataBody, ConfigCreateTimingAck.class);
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleCreateVirtualResponse(BaseLanProtocol var1) {
    #         CreateVirtualEvent var2 = (CreateVirtualEvent) JSON.parseObject(var1.requestDataBody, CreateVirtualEvent.class);
    #         String var3 = TAG;
    #         StringBuilder var4 = new StringBuilder();
    #         var4.append("handleCreateVirtualResponse : ");
    #         var4.append(var2.ack);
    #         LogUtils.d(var3, var4.toString());
    #         var2.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleDeleteCommonMsg(BaseLanProtocol var1) {
    #         byte[] var2 = var1.requestDataBody;
    #         boolean var3 = false;
    #         BaseAck var5 = (BaseAck) JSON.parseObject(var2, BaseAck.class);
    #         DeleteCommonMsgEvent var4 = new DeleteCommonMsgEvent();
    #         if (var5.ack == 1) {
    #             var3 = true;
    #         }
    #
    #         var4.success = var3;
    #         var4.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         RxBus.getInstance().post(var4);
    #     }
    #
    #     public void handleDeleteIrKey(BaseLanProtocol var1) {
    #         byte[] var2 = var1.requestDataBody;
    #         String var3 = TAG;
    #         StringBuilder var4 = new StringBuilder();
    #         var4.append("handleCreateIrKey ack:");
    #         boolean var5 = false;
    #         var4.append(var2[0]);
    #         LogUtils.d(var3, var4.toString());
    #         this.mLanDataRequestModel.requestConfigUnlock();
    #         DeleteIrKeyEvent var6 = new DeleteIrKeyEvent();
    #         var6.deleteFrameId = ConvertUtils.toInt(var1.frameId);
    #         if (var2[0] == 1) {
    #             var5 = true;
    #         }
    #
    #         var6.isSuccess = var5;
    #         RxBus.getInstance().post(var6);
    #     }
    #
    #     public void handleDeleteService(BaseLanProtocol var1) {
    #         BaseAck var2 = (BaseAck) JSON.parseObject(var1.requestDataBody, BaseAck.class);
    #         DeleteServiceResponseEvent var3 = new DeleteServiceResponseEvent();
    #         var3.ack = var2.ack;
    #         var3.frameId = ConvertUtils.toInt(var1.frameId);
    #         RxBus.getInstance().post(var3);
    #     }
    #
    #     public void handleDeleteVirtualResponse(BaseLanProtocol var1) {
    #         BaseAck var2 = (BaseAck) JSON.parseObject(var1.requestDataBody, BaseAck.class);
    #         String var3 = TAG;
    #         StringBuilder var4 = new StringBuilder();
    #         var4.append("handleDeleteVirtualResponse : ");
    #         var4.append(var2.ack);
    #         LogUtils.d(var3, var4.toString());
    #         DeleteVirtualEvent var5 = new DeleteVirtualEvent();
    #         var5.code = var2.ack;
    #         var5.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         RxBus.getInstance().post(var5);
    #     }
    #
    #     public void handleDeviceDelete(BaseLanProtocol var1) {
    #         this.mLanDataRequestModel.requestConfigUnlock();
    #         byte[] var2 = var1.requestDataBody;
    #         boolean var3 = false;
    #         BaseAck var4 = (BaseAck) JSON.parseObject(var2, BaseAck.class);
    #         DeletePhysicalDeviceEvent var5 = new DeletePhysicalDeviceEvent();
    #         if (var4.ack == 1) {
    #             var3 = true;
    #         }
    #
    #         var5.isSuccess = var3;
    #         var5.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         RxBus.getInstance().post(var5);
    #     }
    #
    #     public void handleDeviceHint(BaseLanProtocol var1) {
    #         byte[] var2 = var1.requestDataBody;
    #         if (var2.length == 3) {
    #             boolean var3 = false;
    #             byte var4 = var2[0];
    #             String var5 = TAG;
    #             StringBuilder var6 = new StringBuilder();
    #             var6.append("device hint response state value :");
    #             var6.append(var4);
    #             LogUtils.d(var5, var6.toString());
    #             byte[] var10 = new byte[1];
    #             byte[] var9 = new byte[2];
    #             ByteBuffer var7 = ByteBuffer.wrap(var2);
    #             var7.get(var10);
    #             var7.get(var9);
    #             DeviceHintEvent var8 = new DeviceHintEvent();
    #             if (var4 == 1) {
    #                 var3 = true;
    #             }
    #
    #             var8.isFlash = var3;
    #             var8.deviceAddress = com.leelen.sdk.core.utils.ConvertUtils.toUnsignedShort(var9);
    #             var8.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #             RxBus.getInstance().post(var8);
    #         }
    #
    #     }
    #
    #     public void handleDeviceInvite(BaseLanProtocol var1) {
    #         BaseAck var2 = (BaseAck) JSON.parseObject(var1.requestDataBody, BaseAck.class);
    #         String var4 = TAG;
    #         StringBuilder var3 = new StringBuilder();
    #         var3.append("handleDeviceInvite ack:");
    #         var3.append(var2.ack);
    #         LogUtils.d(var4, var3.toString());
    #     }
    #
    #     public void handleDeviceReplace(BaseLanProtocol var1) {
    #         byte[] var2 = var1.requestDataBody;
    #         boolean var3 = false;
    #         BaseAck var5 = (BaseAck) JSON.parseObject(var2, BaseAck.class);
    #         RequestReplaceEvent var4 = new RequestReplaceEvent();
    #         if (var5.ack == 1) {
    #             var3 = true;
    #         }
    #
    #         var4.requestSuccess = var3;
    #         var4.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         RxBus.getInstance().post(var4);
    #     }
    #
    #     public void handleDeviceReplaceStatus(BaseLanProtocol var1) {
    #         DeviceReplaceRes var4 = (DeviceReplaceRes) JSON.parseObject(var1.requestDataBody, DeviceReplaceRes.class);
    #         String var2 = TAG;
    #         StringBuilder var3 = new StringBuilder();
    #         var3.append("handleDeviceReplaceStatus() status:");
    #         var3.append(var4.status);
    #         LogUtils.d(var2, var3.toString());
    #         RxBus.getInstance().post(var4);
    #     }
    #
    #     public void handleDeviceStatus(BaseLanProtocol var1) {
    #         DeviceStatusLanProtocol.getInstance().updateDeviceStatus(var1);
    #     }
    #
    #     public void handleDeviceUpgradeInfoResponse(BaseLanProtocol var1) {
    #         byte[] var2 = var1.payloadType;
    #         DeviceUpgradeInfoListEvent var3 = new DeviceUpgradeInfoListEvent();
    #         var3.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         if (var2[0] == 1) {
    #             var3.list = JSON.parseArray(new String(var1.requestDataBody), DeviceUpgradeInfo.class);
    #             var3.state = 1;
    #         } else {
    #             byte[] var4 = var1.requestDataBody;
    #             if (var4 != null) {
    #                 var3.state = var4[0];
    #             }
    #         }
    #
    #         RxBus.getInstance().post(var3);
    #     }
    #
    #     public void handleDeviceUpgradeProgressResponse(BaseLanProtocol var1) {
    #         byte[] var2 = var1.requestDataBody;
    #         if (var2 != null) {
    #             byte[] var3 = new byte[1];
    #             byte[] var5 = new byte[2];
    #             byte[] var4 = new byte[2];
    #             ByteBuffer var6 = ByteBuffer.wrap(var2);
    #             var6.get(var3);
    #             var6.get(var5);
    #             var6.get(var4);
    #             UpgradeBean var7 = new UpgradeBean();
    #             var7.status = var3[0];
    #             var7.address = com.leelen.sdk.core.utils.ConvertUtils.toShort(var5);
    #             var7.progress = com.leelen.sdk.core.utils.ConvertUtils.toShort(var4);
    #             RxBus.getInstance().post(var7);
    #         }
    #
    #     }
    #
    #     public void handleEnvironmentSupportType(BaseLanProtocol var1) {
    #         String var2 = new String(var1.requestDataBody);
    #         String var3 = TAG;
    #         StringBuilder var4 = new StringBuilder();
    #         var4.append("handleEnvironmentSupportType() body : ");
    #         var4.append(var2);
    #         LogUtils.d(var3, var4.toString());
    #         EnvironmentSupportTypeData var5 = (EnvironmentSupportTypeData) JSON.parseObject(var1.requestDataBody, EnvironmentSupportTypeData.class);
    #         RxBus.getInstance().post(var5);
    #     }
    #
    #     public void handleFileRead(BaseLanProtocol var1) {
    # //        WeakReference var2 = FileReadLanProtocol.getInstance().getFileReadAck(var1);
    # //        RxBus.getInstance().post(var2.get());
    #     }
    #
    #     public void handleFileReadOrWriteReq(BaseLanProtocol var1, boolean var2) {
    #         byte[] var3 = var1.requestDataBody;
    #         if (var3.length == 5) {
    #             byte[] var4 = new byte[1];
    #             byte[] var5 = new byte[4];
    #             ByteBuffer var8 = ByteBuffer.wrap(var3);
    #             var8.get(var4);
    #             var8.get(var5);
    #             byte var6;
    #             String var7;
    #             StringBuilder var11;
    #             if (var2) {
    #                 FileReadReqEvent var9 = new FileReadReqEvent();
    #                 var6 = var4[0];
    #                 var7 = TAG;
    #                 var11 = new StringBuilder();
    #                 var11.append("handleFileReadOrWriteReq() read ack value : ");
    #                 var11.append(var6);
    #                 LogUtils.d(var7, var11.toString());
    #                 var9.ack = var6;
    #                 var9.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #                 if (var6 == 1) {
    #                     var9.fileHandle = com.leelen.sdk.core.utils.ConvertUtils.toInt(var5);
    #                 }
    #
    #                 RxBus.getInstance().post(var9);
    #             } else {
    #                 FileWriteReqEvent var10 = new FileWriteReqEvent();
    #                 var6 = var4[0];
    #                 var7 = TAG;
    #                 var11 = new StringBuilder();
    #                 var11.append("handleFileReadOrWriteReq() write ack value : ");
    #                 var11.append(var6);
    #                 LogUtils.d(var7, var11.toString());
    #                 var10.ack = var6;
    #                 var10.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #                 if (var6 == 1) {
    #                     var10.fileHandle = com.leelen.sdk.core.utils.ConvertUtils.toInt(var5);
    #                 }
    #
    #                 RxBus.getInstance().post(var10);
    #             }
    #         }
    #
    #     }
    #
    #     public void handleGatewayDevice(BaseLanProtocol var1) {
    #         BaseAck var2 = (BaseAck) JSON.parseObject(var1.requestDataBody, BaseAck.class);
    #         String var3 = TAG;
    #         StringBuilder var4 = new StringBuilder();
    #         var4.append("gateway invite response state value :");
    #         var4.append(var2.ack);
    #         LogUtils.d(var3, var4.toString());
    #         AddGatewayEvent var5 = new AddGatewayEvent();
    #         var5.addFrameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         var5.code = var2.ack;
    #         RxBus.getInstance().post(var5);
    #     }
    #
    #     public void handleGatewayFeedbackDevice(BaseLanProtocol var1) {
    #         GatewayFeedback var4 = (GatewayFeedback) JSON.parseObject(var1.requestDataBody, GatewayFeedback.class);
    #         String var2 = TAG;
    #         StringBuilder var3 = new StringBuilder();
    #         var3.append("gateway feedback response state value :");
    #         var3.append(var4.status);
    #         LogUtils.d(var2, var3.toString());
    #         GatewayFeedbackEvent var5 = new GatewayFeedbackEvent();
    #         var5.code = var4.status;
    #         RxBus.getInstance().post(var5);
    #     }
    #
    #     public void handleGet485ProtocolList(BaseLanProtocol var1) {
    #         ProtocolListEvent var2 = (ProtocolListEvent) JSON.parseObject(var1.requestDataBody, ProtocolListEvent.class);
    #         var2.frameId = ConvertUtils.toInt(var1.frameId);
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleGetCloudStatus(BaseLanProtocol var1) {
    #         ConnectServerInfo var2 = (ConnectServerInfo) JSON.parseObject(var1.requestDataBody, ConnectServerInfo.class);
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleGetDeviceLocation(BaseLanProtocol var1) {
    #         DeviceLocation var2 = (DeviceLocation) JSON.parseObject(var1.requestDataBody, DeviceLocation.class);
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleGetDeviceStatus(BaseLanProtocol var1) {
    #         byte[] var2 = var1.requestDataBody;
    #         if (var2.length == 4) {
    #             byte[] var3 = new byte[1];
    #             byte[] var4 = new byte[2];
    #             byte[] var6 = new byte[1];
    #             ByteBuffer var7 = ByteBuffer.wrap(var2);
    #             var7.get(var3);
    #             var7.get(var4);
    #             var7.get(var6);
    #             if (var3[0] == 0) {
    #                 return;
    #             }
    #
    #             int var5 = com.leelen.sdk.core.utils.ConvertUtils.toUnsignedShort(var4);
    #             String var9 = TAG;
    #             StringBuilder var8 = new StringBuilder();
    #             var8.append("handleGetDeviceStatus() device address : ");
    #             var8.append(var5);
    #             var8.append(" status : ");
    #             var8.append(var6[0]);
    #             LogUtils.d(var9, var8.toString());
    #             DeviceStateModel.getInstance().addOrUpdateDeviceState(var5, var6[0]);
    #             RxBus.getInstance().post(new DeviceStatusUpdateEvent());
    #         }
    #
    #     }
    #
    #     public void handleGetDiyProtocol(BaseLanProtocol var1) {
    #         DiyProtocolResponse var2 = (DiyProtocolResponse) JSON.parseObject(var1.requestDataBody, DiyProtocolResponse.class);
    #         var2.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         String var3 = TAG;
    #         StringBuilder var4 = new StringBuilder();
    #         var4.append("handleGetDiyProtocol : ");
    #         var4.append(var2.ack);
    #         LogUtils.d(var3, var4.toString());
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleGetDiyProtocolList(BaseLanProtocol var1) {
    #         DiyProtocolListEvent var2 = (DiyProtocolListEvent) JSON.parseObject(var1.requestDataBody, DiyProtocolListEvent.class);
    #         var2.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleGetEnvironmentBindData(BaseLanProtocol var1) {
    #         String var2 = new String(var1.requestDataBody);
    #         String var3 = TAG;
    #         StringBuilder var4 = new StringBuilder();
    #         var4.append("handleGetEnvironmentBindData() body : ");
    #         var4.append(var2);
    #         LogUtils.d(var3, var4.toString());
    #         EnvironmentBindData var5 = (EnvironmentBindData) JSON.parseObject(var1.requestDataBody, EnvironmentBindData.class);
    #         RxBus.getInstance().post(var5);
    #     }
    #
    #     public void handleGetLockMemberListResponse(BaseLanProtocol var1) {
    #         BaseAck var2 = (BaseAck) JSON.parseObject(var1.requestDataBody, BaseAck.class);
    #         GetLockMemberResponseEvent var3 = new GetLockMemberResponseEvent();
    #         var3.ack = var2.ack;
    #         var3.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         RxBus.getInstance().post(var3);
    #     }
    #
    #     public void handleGetQuickControlData(BaseLanProtocol var1) {
    #         String var2 = new String(var1.requestDataBody);
    #         String var3 = TAG;
    #         StringBuilder var4 = new StringBuilder();
    #         var4.append("handleGetQuickControlData() body : ");
    #         var4.append(var2);
    #         LogUtils.d(var3, var4.toString());
    #         QuickControlBindData var5 = (QuickControlBindData) JSON.parseObject(var1.requestDataBody, QuickControlBindData.class);
    #         RxBus.getInstance().post(var5);
    #     }
    #
    #     public void handleGetRealTemporaryPasswordResponse(BaseLanProtocol var1) {
    #         GetRealTemporaryPasswordAck var2 = (GetRealTemporaryPasswordAck) JSON.parseObject(var1.requestDataBody, GetRealTemporaryPasswordAck.class);
    #         var2.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleGetRemoteDebug(BaseLanProtocol var1) {
    #         String var2 = new String(var1.requestDataBody);
    #         String var3 = TAG;
    #         StringBuilder var4 = new StringBuilder();
    #         var4.append("handleGetRemoteDebug() body : ");
    #         var4.append(var2);
    #         LogUtils.d(var3, var4.toString());
    #         RemoteResponseBean var5 = (RemoteResponseBean) JSON.parseObject(var1.requestDataBody, RemoteResponseBean.class);
    #         var5.ack = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
    #         RxBus.getInstance().post(var5);
    #     }
    #
    #     public void handleGetVoiceAlarm(BaseLanProtocol var1) {
    #         VoiceAlarmData var2 = (VoiceAlarmData) JSON.parseObject(var1.requestDataBody, VoiceAlarmData.class);
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleGetVoiceSkill(BaseLanProtocol var1) {
    #         VoiceSkillData var2 = (VoiceSkillData) JSON.parseObject(var1.requestDataBody, VoiceSkillData.class);
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleIpcBindLanResponse(BaseLanProtocol var1) {
    #         BindAck var2 = (BindAck) JSON.parseObject(var1.requestDataBody, BindAck.class);
    #         String var4 = TAG;
    #         StringBuilder var3 = new StringBuilder();
    #         var3.append("bind ipc ack : ");
    #         var3.append(var2.ack);
    #         LogUtils.d(var4, var3.toString());
    #         if (var2.bind_account != null) {
    #             var3 = new StringBuilder();
    #             var3.append("bind ipc ack bind account: ");
    #             var3.append(var2.bind_account);
    #             LogUtils.d(var4, var3.toString());
    #         }
    #
    #         RxBus.getInstance().post(var2);
    #     }
    #
    #     public void handleIpcUnBindLanResponse(BaseLanProtocol var1) {
    #         BaseAck var4 = (BaseAck) JSON.parseObject(var1.requestDataBody, BaseAck.class);
    #         String var2 = TAG;
    #         StringBuilder var3 = new StringBuilder();
    #         var3.append("unbind ipc ack : ");
    #         var3.append(var4.ack);
    #         LogUtils.d(var2, var3.toString());
    #         IpcUnBindEvent var5 = new IpcUnBindEvent();
    #         var5.code = var4.ack;
    #         RxBus.getInstance().post(var5);
    #     }
    #
    #     public void handleLocalHistoryPassThroughResponse(BaseLanProtocol var1) {
    #         byte[] var2 = var1.requestDataBody;
    #         if (var2 != null) {
    #             byte[] var3 = new byte[1];
    #             byte[] var4 = new byte[2];
    #             byte[] var5 = new byte[2];
    #             byte[] var10 = new byte[2];
    #             ByteBuffer var11 = ByteBuffer.wrap(var2);
    #             var11.get(var3);
    #             LocalHistory var6 = new LocalHistory();
    #             String var7 = TAG;
    #             StringBuilder var8 = new StringBuilder();
    #             var8.append("handleLocalHistoryPassThroughResponse() ack : ");
    #             var8.append(var3[0]);
    #             LogUtils.d(var7, var8.toString());
    #             if (var3[0] != 1) {
    #                 var6.isSuccess = false;
    #             } else {
    #                 var11.get(var4);
    #                 var11.get(var5);
    #                 var11.get(var10);
    #                 ArrayList var14 = new ArrayList();
    #
    #                 for (int var9 = 0; var9 < com.leelen.sdk.core.utils.ConvertUtils.toShort(var10); ++var9) {
    #                     byte[] var12 = new byte[1];
    #                     var4 = new byte[2];
    #                     var3 = new byte[1];
    #                     var5 = new byte[4];
    #                     var11.get(var12);
    #                     var11.get(var4);
    #                     var11.get(var3);
    #                     var11.get(var5);
    #                     LocalRecordRes var13 = new LocalRecordRes();
    #                     var13.userId = var4;
    #                     var13.opType = var3[0];
    #                     var13.timeStamp = com.leelen.sdk.core.utils.ConvertUtils.toUnsignedInt(var5);
    #                     var14.add(var13);
    #                 }
    #
    #                 var6.list = var14;
    #                 var6.isSuccess = true;
    #             }
    #
    #             RxBus.getInstance().post(var6);
    #         }
    #
    #     }
    #

#     public void handleLoginLanResponse(BaseLanProtocol var1, Handler var2) {
#         int var3 = ((LoginAck) com.alibaba.fastjson2.JSON.parseObject(var1.requestDataBody, LoginAck.class)).ack;
#         String var4 = TAG;
#         StringBuilder var5 = new StringBuilder();
#         var5.append("login success ? = ");
#         var5.append(var3);
#         LogUtils.d(var4, var5.toString());
#         GatewayInfo.getInstance().setTcpServerCode(var1.serverId);
#         Message var6 = var2.obtainMessage();
#         var6.what = 2;
#         var6.arg1 = var3;
#         var6.sendToTarget();
#     }
#
#     public void handleLogoutResponse(BaseLanProtocol var1) {
#         byte[] var5 = var1.requestDataBody;
#         boolean var2 = false;
#         int var3 = ((BaseAck) JSON.parseObject(var5, BaseAck.class)).ack;
#         String var6 = TAG;
#         StringBuilder var4 = new StringBuilder();
#         var4.append("logout success ? ");
#         var4.append(var3);
#         LogUtils.d(var6, var4.toString());
#         LogoutLanEvent var7 = new LogoutLanEvent();
#         if (var3 == 1) {
#             var2 = true;
#         }
#
#         var7.logoutSuc = var2;
#         RxBus.getInstance().post(var7);
#     }
#
#     public void handleManuallyAddCondition(BaseLanProtocol var1) {
#         byte[] var2 = var1.requestDataBody;
#         int var3 = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
#         int var4 = var2.length;
#         boolean var5 = true;
#         if (var4 == 1) {
#             byte var9 = var2[0];
#             String var6 = TAG;
#             StringBuilder var8 = new StringBuilder();
#             var8.append("manually add condition response state value :");
#             var8.append(var9);
#             LogUtils.d(var6, var8.toString());
#             ManuallyAddConditionEvent var7 = new ManuallyAddConditionEvent();
#             var7.frameId = var3;
#             if (var9 != 1) {
#                 var5 = false;
#             }
#
#             var7.isSuc = var5;
#             var7.code = var9;
#             RxBus.getInstance().post(var7);
#         }
#
#     }
#
#     public void handleModifyGatewayName(BaseLanProtocol var1) {
#         byte[] var4 = var1.requestDataBody;
#         boolean var2 = false;
#         BaseAck var3 = (BaseAck) JSON.parseObject(var4, BaseAck.class);
#         ModifyGatewayNameResultEvent var5 = new ModifyGatewayNameResultEvent();
#         if (var3.ack == 1) {
#             var2 = true;
#         }
#
#         var5.isSuccess = var2;
#         RxBus.getInstance().post(var5);
#     }
#
#     public void handleQuickControlSupportType(BaseLanProtocol var1) {
#         String var2 = new String(var1.requestDataBody);
#         String var3 = TAG;
#         StringBuilder var4 = new StringBuilder();
#         var4.append("handleQuickControlSupportType() body : ");
#         var4.append(var2);
#         LogUtils.d(var3, var4.toString());
#         QuickControlSupportTypeData var5 = (QuickControlSupportTypeData) JSON.parseObject(var1.requestDataBody, QuickControlSupportTypeData.class);
#         RxBus.getInstance().post(var5);
#     }
#
#     public void handleRandomKeyResponse(BaseLanProtocol var1, Handler var2) {
#         LogUtils.d(TAG, "handleRandomKeyResponse()");
#         String var3 = ((RandomAck) com.alibaba.fastjson2.JSON.parseObject(var1.requestDataBody,RandomAck.class)).random;
#         LogUtils.d(TAG, "handleRandomKeyResponse()："+ var3);
#         Message var4 = var2.obtainMessage();
#         var4.what = 1;
#         var4.obj = var3;
#         var4.sendToTarget();
#     }
#
#     public void handleSetDeviceLocation(BaseLanProtocol var1) {
#         String var2 = new String(var1.requestDataBody);
#         String var3 = TAG;
#         StringBuilder var4 = new StringBuilder();
#         var4.append("handleSetDeviceLocation() body : ");
#         var4.append(var2);
#         LogUtils.d(var3, var4.toString());
#         byte[] var6 = var1.requestDataBody;
#         boolean var5 = false;
#         BaseAck var8 = (BaseAck) JSON.parseObject(var6, BaseAck.class);
#         SetDeviceLocationResponseEvent var7 = new SetDeviceLocationResponseEvent();
#         if (var8.ack == 1) {
#             var5 = true;
#         }
#
#         var7.success = var5;
#         RxBus.getInstance().post(var7);
#     }
#
#     public void handleSetDiyProtocolList(BaseLanProtocol var1) {
#         BaseAck var2 = (BaseAck) JSON.parseObject(var1.requestDataBody, BaseAck.class);
#         SetDiyProtocolEvent var3 = (SetDiyProtocolEvent) JSON.parseObject(var1.requestDataBody, SetDiyProtocolEvent.class);
#         var3.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
#         var3.ack = var2.ack;
#         RxBus.getInstance().post(var3);
#     }
#
#     public void handleSetEnvironmentBindDataResponse(BaseLanProtocol var1) {
#         byte[] var4 = var1.requestDataBody;
#         boolean var2 = false;
#         BaseAck var3 = (BaseAck) JSON.parseObject(var4, BaseAck.class);
#         SetEnvironmentBindDataResponseEvent var5 = new SetEnvironmentBindDataResponseEvent();
#         if (var3.ack == 1) {
#             var2 = true;
#         }
#
#         var5.success = var2;
#         RxBus.getInstance().post(var5);
#     }
#
#     public void handleSetQuickControlData(BaseLanProtocol var1) {
#         String var2 = new String(var1.requestDataBody);
#         String var3 = TAG;
#         StringBuilder var4 = new StringBuilder();
#         var4.append("handleSetQuickControlData() body : ");
#         var4.append(var2);
#         LogUtils.d(var3, var4.toString());
#         byte[] var6 = var1.requestDataBody;
#         boolean var5 = false;
#         BaseAck var8 = (BaseAck) JSON.parseObject(var6, BaseAck.class);
#         SetQuickControlBindDataResponseEvent var7 = new SetQuickControlBindDataResponseEvent();
#         if (var8.ack == 1) {
#             var5 = true;
#         }
#
#         var7.success = var5;
#         RxBus.getInstance().post(var7);
#     }
#
#     public void handleSmartPanelAdd(BaseLanProtocol var1) {
#         byte[] var4 = var1.requestDataBody;
#         boolean var2 = false;
#         BaseAck var3 = (BaseAck) JSON.parseObject(var4, BaseAck.class);
#         SmartPanelAddResultEvent var5 = new SmartPanelAddResultEvent();
#         if (var3.ack == 1) {
#             var2 = true;
#         }
#
#         var5.isSuccess = var2;
#         RxBus.getInstance().post(var5);
#     }
#
#     public void handleSubmitVoiceAlarm(BaseLanProtocol var1) {
#         String var2 = new String(var1.requestDataBody);
#         String var3 = TAG;
#         StringBuilder var4 = new StringBuilder();
#         var4.append("handleSubmitVoiceAlarm() body : ");
#         var4.append(var2);
#         LogUtils.d(var3, var4.toString());
#         byte[] var6 = var1.requestDataBody;
#         boolean var5 = false;
#         BaseAck var7 = (BaseAck) JSON.parseObject(var6, BaseAck.class);
#         SubmitVoiceAlarmResponseEvent var8 = new SubmitVoiceAlarmResponseEvent();
#         if (var7.ack == 1) {
#             var5 = true;
#         }
#
#         var8.success = var5;
#         RxBus.getInstance().post(var8);
#     }
#
#     public void handleSubmitVoiceSkill(BaseLanProtocol var1) {
#         String var2 = new String(var1.requestDataBody);
#         String var3 = TAG;
#         StringBuilder var4 = new StringBuilder();
#         var4.append("handleSubmitVoiceSkill() body : ");
#         var4.append(var2);
#         LogUtils.d(var3, var4.toString());
#         byte[] var6 = var1.requestDataBody;
#         boolean var5 = false;
#         BaseAck var7 = (BaseAck) JSON.parseObject(var6, BaseAck.class);
#         SubmitVoiceSkillResponseEvent var8 = new SubmitVoiceSkillResponseEvent();
#         if (var7.ack == 1) {
#             var5 = true;
#         }
#
#         var8.success = var5;
#         RxBus.getInstance().post(var8);
#     }
#
#     public void handleSyncIrCode(BaseLanProtocol var1) {
#         BaseAck var2 = (BaseAck) JSON.parseObject(var1.requestDataBody, BaseAck.class);
#         IrSyncCodeEvent var3 = new IrSyncCodeEvent();
#         var3.code = var2.ack;
#         var3.syncIrCodeFrameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
#         RxBus.getInstance().post(var3);
#     }
#
#     public void handleUpdateDeviceStatus(BaseLanProtocol var1) {
#         byte[] var2 = var1.requestDataBody;
#         if (var2.length == 3) {
#             byte[] var6 = new byte[2];
#             byte[] var3 = new byte[1];
#             ByteBuffer var8 = ByteBuffer.wrap(var2);
#             var8.get(var6);
#             var8.get(var3);
#             int var4 = com.leelen.sdk.core.utils.ConvertUtils.toUnsignedShort(var6);
#             byte var5 = var3[0];
#             String var9 = TAG;
#             StringBuilder var7 = new StringBuilder();
#             var7.append("handleUpdateDeviceStatus() device address : ");
#             var7.append(var4);
#             var7.append(" status : ");
#             var7.append(var5);
#             LogUtils.d(var9, var7.toString());
#             DeviceStateModel.getInstance().updateDeviceStateByDeviceAddress(var4, var5);
#         }
#
#     }
#
#     public void handleUpdateRemoteDebug(BaseLanProtocol var1) {
#         UpdateRemoteDebugAckEvent var2 = (UpdateRemoteDebugAckEvent) JSON.parseObject(var1.requestDataBody, UpdateRemoteDebugAckEvent.class);
#         var2.frameId = com.leelen.sdk.core.utils.ConvertUtils.toInt(var1.frameId);
#         RxBus.getInstance().post(var2);
#     }
#
#     public void handleUpdateSensorStatus(BaseLanProtocol var1) {
#         byte[] var2 = var1.requestDataBody;
#         if (var2.length == 3) {
#             byte[] var3 = new byte[2];
#             byte[] var6 = new byte[1];
#             ByteBuffer var8 = ByteBuffer.wrap(var2);
#             var8.get(var3);
#             var8.get(var6);
#             int var4 = ConvertUtils.toUnsignedShort(var3);
#             byte var5 = var6[0];
#             String var9 = TAG;
#             StringBuilder var7 = new StringBuilder();
#             var7.append("handleUpdateSensorStatus() logic address : ");
#             var7.append(var4);
#             var7.append(" status : ");
#             var7.append(var5);
#             LogUtils.d(var9, var7.toString());
#             SensorStateModel.getInstance().updateSensorStateBySensorAddress(var4, var5);
#         }
#
#     }
#
#     private static class SingletonInstance {
#         private static final LanDataResponseHandleModel INSTANCE = new LanDataResponseHandleModel();
#
#         private SingletonInstance() {
#         }
#     }
# }
