import base64
import threading

from ...utils.LogUtils import LogUtils
from ...common.LeelenType import *
from ..BaseDaoBean import BaseDaoBean
from ...entity.GatewayInfo import GatewayInfo
from ...entity.LogicServer import LogicServer
from ...handler.DeviceStatusEvent import DeviceStatusEvent
from ...handler.FlowRxBus import FlowRxBus
from ...models.LogicServerStateModel import LogicServerStateModel
from ...utils.Base64Utils import Base64Utils


class AckToDao:
    _instance = None

    COMMA_REX = ","
    LINE_REX = r"\n"
    TAG = "AckToDao"

    def __init__(self):
        self.m_value_list: list[str] = []
        self.m_field_list: list[str] = []
        self.mAddDeviceAddressList: list[int] = []
        self.register_fetch_complete_event()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = AckToDao()
        return cls._instance

    def register_fetch_complete_event(self):
        # TODO: 这里你需要补充事件监听的实现逻辑
        pass

    def get_operate_type(self, op_type: str) -> int:
        if op_type.lower() == "insert":
            return 1
        elif op_type.lower() == "update":
            return 2
        else:
            return 3

    def trans_device_state_data(self, keys, data_list):
        """
        keys: List[str] - 类似 ["dev_addr", "state", ...]
        data_list: List[str] - 每个元素是类似 "1,2,3" 的字符串
        """
        for item in data_list:
            split = item.split(',')
            if len(split) == len(keys):
                index_of_addr = keys.index("dev_addr") if "dev_addr" in keys else -1
                index_of_state = keys.index("state") if "state" in keys else -1

                address = int(split[index_of_addr]) if index_of_addr != -1 else 0
                state = int(split[index_of_state]) if index_of_state != -1 else 0

                # print(f"增加设备状态信息：address = {address}; state = {state}")
                # DeviceStateModel.get_instance().add_or_update_device_state(address, state)

    def trans_logic_server_state_data(self, field_list, row_list):
        model = LogicServerStateModel.get_instance()

        for row in row_list:
            fields = row.split(',')
            if len(fields) != len(field_list):
                continue

            try:
                logic_addr_index = field_list.index("logic_addr")
                func_id_index = field_list.index("func_id")
                state_index = field_list.index("state")
            except ValueError:
                continue

            try:
                logic_addr = int(fields[logic_addr_index]) if logic_addr_index != -1 else 0
                func_id = int(fields[func_id_index]) if func_id_index != -1 else 0
            except ValueError:
                continue

            state_bytes = None
            if state_index != -1:
                try:
                    state_bytes = base64.b64decode(fields[state_index])
                except Exception as e:
                    LogUtils.e("LogicServerStateModel", f"base64 stateIndex exception : {e}")
                    continue

            if state_bytes is None:
                continue

            device_state = model.get_array_by_address(logic_addr)
            should_post_event = True

            if device_state is None:
                device_state = {}
            else:
                previous_state = device_state.get(func_id)

                if func_id in (55318, 53268, 43029) and previous_state is not None:
                    if previous_state[0] == 0 and state_bytes[0] == 0:
                        should_post_event = True
                    else:
                        should_post_event = False

                # if previous_state is not None:
                #     if np.array_equal(np.frombuffer(previous_state, dtype=np.uint8),
                #                       np.frombuffer(state_bytes, dtype=np.uint8)):
                #         should_post_event = False

            if should_post_event:
                device_event = DeviceStatusEvent()
                device_event.logic_address = logic_addr
                device_event.function_id = func_id
                device_event.state = state_bytes
                FlowRxBus.get_instance().post(device_event)

                # if func_id in [18442, 22529, 16395, 18455]:
                #     env_event = EnvironmentStatusEvent()
                #     env_event.logic_address = logic_addr
                #     env_event.function_id = func_id
                #     FlowRxBus.get_instance().post(env_event)

            device_state[func_id] = state_bytes
            model.add_or_update_state(logic_addr, device_state)

    def trans_device_data(self, operate_type: str, keys: list[str], rows: list[str]):
        print("转换设备")
        device_list = []
        gateway_desc = GatewayInfo.get_instance().get_gateway_desc_string()

        for row in rows:
            split = row.split(',')
            if len(split) == len(keys):
                device = Device()
                device.gateway_address = gateway_desc

                index_map = {key: keys.index(key) for key in keys}

                # def safe_get(key, default=0, decode=False, long_val=False):
                #     idx = index_map.get(key, -1)
                #     if idx == -1: return None
                #     try:
                #         val = split[idx]
                #         if decode:
                #             return Base64Utils.decode(val)
                #         return int(val) if not long_val else int(val)
                #     except Exception as e:
                #         print(f"字段 {key} 处理异常: {e}")
                #         return default

                # device.dev_addr = safe_get(Device.DEV_ADDR, 0)
                # device.dev_type = safe_get(Device.DEV_TYPE, 0)
                # device.soft_version = safe_get(Device.SOFT_VERSION, "", decode=True)
                # device.dev_name = split[index_map.get(Device.DEV_NAME, -1)] if Device.DEV_NAME in keys else ""
                # device.dip = split[index_map.get(Device.DIP, -1)] if Device.DIP in keys else ""
                # device.sn = safe_get(Device.SN, "", decode=True)
                # device.srv_num = safe_get(Device.SRV_NUM, 0)
                # device.room_id = safe_get(Device.ROOM_ID, 0)
                # device.create_time = safe_get(BaseDaoBean.CREATE_TIME, 0, long_val=True)
                # device.update_time = safe_get(BaseDaoBean.UPDATE_TIME, 0, long_val=True)
                #
                # device_list.append(device)

        # if operate_type.lower() not in [LeelenType.TableOperateType.TYPE_INSERT,
        #                                 LeelenType.TableOperateType.TYPE_UPDATE]:
        #     DeviceDao.get_instance().delete_device_list(device_list)
        #     return
        #
        # print("设备添加1")
        # DeviceDao.get_instance().add_or_update_device_list(device_list)
        #
        # if operate_type.lower() == LeelenType.TableOperateType.TYPE_INSERT:
        #     print("设备添加2")
        #     for dev in device_list:
        #         self.m_add_device_address_list.append(dev.dev_addr)
        #         print("设备添加3")
        #         FlowRxBus.get_instance().post(dev)

    def trans_logic_server_data(self, op_type: str, keys: list[str], rows: list[str]):
        logic_server_list = []
        update_bean_list = []
        gateway_address = GatewayInfo.get_instance().get_gateway_desc_string()
        key_index = {k: i for i, k in enumerate(keys)}

        for row in rows:
            split = row.split(',')
            if len(split) != len(keys):
                continue

            def get_int(key: str, default=0):
                try:
                    return int(split[key_index[key]]) if key in key_index else default
                except:
                    return default

            def get_str(key: str, default=""):
                return split[key_index[key]] if key in key_index else default

            def get_base64(key: str, default=""):
                try:
                    return Base64Utils.decode(split[key_index[key]]) if key in key_index else default
                except Exception as e:
                    LogUtils.e("LogicServerProcessor", f"Base64 decode failed for {key}: {e}")
                    return default

            logic = LogicServer()
            logic.gateway_address = gateway_address
            logic.logic_addr = get_int(LogicServer.LOGIC_ADDR)
            logic.dev_addr = get_int(LogicServer.DEV_ADDR)
            logic.srv_id = get_int(LogicServer.SRV_ID)
            logic.srv_type = get_int(LogicServer.SRV_TYPE)
            logic.storage_type = get_int(LogicServer.STORAGE_TYPE)
            logic.logic_type = get_int(LogicServer.LOGIC_TYPE)
            logic.func_grp_num = get_int(LogicServer.FUNC_GRP_NUM)
            logic.func_grp_id = get_base64(LogicServer.FUNC_GRP_ID)
            logic.display = get_int(LogicServer.DISPLAY)
            logic.icon_id = get_int(LogicServer.ICON_ID)
            logic.logic_name = get_str(LogicServer.LOGIC_NAME)
            logic.room_id = get_int(LogicServer.ROOM_ID)
            logic.create_time = get_int(BaseDaoBean.CREATE_TIME, 0)
            logic.update_time = get_int(BaseDaoBean.UPDATE_TIME, 0)

            logic_server_list.append(logic)

            # bean = LogicServerUpdateBean()
            # bean.set_logic_address(logic.logic_addr)
            # bean.set_icon_id(logic.icon_id)
            # bean.set_logic_type(logic.logic_type)
            # bean.set_display(logic.display)
            # bean.set_logic_name(logic.logic_name)
            # bean.set_room_id(logic.room_id)
            # bean.set_operate_type(op_type.strip().lower())
            # update_bean_list.append(bean)

        # dao = LogicServerDao.get_instance()
        # if op_type.lower() in ["insert", "update"]:
        #     dao.add_or_update_logic_server_list(logic_server_list)
        # else:
        #     dao.delete_logic_server_list(logic_server_list)
        #
        # event = LogicServerUpdateEvent()
        # event.list = update_bean_list
        # RxBus.get_instance().post(event)

    def transform_by_table(self, fetch_config_mod_ack, field_list: list[str], value_list: list[str]):
        tbl = fetch_config_mod_ack.tbl.lower()
        op_type = fetch_config_mod_ack.type

        LogUtils.i(f"获取table {tbl}数据 {op_type} : {fetch_config_mod_ack} {field_list} {value_list}")

        if tbl == GatewayTable.FLOOR_TABLE_NAME.lower():
            pass
            # self.trans_floor_data(op_type, field_list, value_list)
        elif tbl == GatewayTable.DEVICE_STATE_TABLE_NAME.lower():
            self.trans_device_state_data(field_list, value_list)
        elif tbl == GatewayTable.DEVICE_TABLE_NAME.lower():
            self.trans_device_data(op_type, field_list, value_list)
        elif tbl == GatewayTable.LOGIC_SERVER_STATE_TABLE_NAME.lower():
            self.trans_logic_server_state_data(field_list, value_list)
        # elif tbl == GatewayTable.ROOM_TABLE_NAME.lower():
        #     self.trans_room_data(op_type, field_list, value_list)
        elif tbl == GatewayTable.LOGIC_SERVER_TABLE_NAME.lower():
            self.trans_logic_server_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.SCENE_TABLE_NAME.lower():
        #     self.trans_scene_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.SCENE_CTRL_TABLE_NAME.lower():
        #     self.trans_scene_ctrl_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.PROPERTY_TABLE_NAME.lower():
        #     self.trans_property_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.LINKAGE_TABLE_NAME.lower():
        #     self.trans_linkage_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.LINKAGE_CTRL_TABLE_NAME.lower():
        #     self.trans_linkage_ctrl_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.LINKAGE_COND_TABLE_NAME.lower():
        #     self.trans_linkage_cond_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.TIMER_TABLE_NAME.lower():
        #     self.trans_timer_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.TIMER_CONTROL_TABLE_NAME.lower():
        #     self.trans_timer_control_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.IR_KEY_TABLE_NAME.lower():
        #     self.trans_ir_key_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.SERIAL_PORT_TABLE_NAME.lower():
        #     self.trans_ir_port_key_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.ACCOUNT_TABLE_NAME.lower():
        #     self.trans_account_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.MSG_STORAGE_LOCK_TABLE_NAME.lower():
        #     self.trans_lock_msg_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.APP_STORAGE_TABLE_NAME.lower():
        #     self.trans_app_storage_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.MSG_STORAGE_COMMON_TABLE_NAME.lower():
        #     self.trans_common_msg_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.TEMPORARY_USER_TABLE_NAME.lower():
        #     self.trans_temporary_user_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.SCHEDULE_STORAGE_TABLE_NAME.lower():
        #     self.trans_schedule_storage_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.ARM_TABLE_NAME.lower():
        #     self.trans_arm_data(op_type, field_list, value_list)
        # elif tbl == GatewayTable.SENSOR_STATE_TABLE_NAME.lower():
        #     self.trans_sensor_state_data(field_list, value_list)

    def transform_data(self, fetch_config_mod_ack):

        LogUtils.i(f"transform_data 数据 {fetch_config_mod_ack} ")


        with threading.Lock():  # 模拟 synchronized(this)
            content = fetch_config_mod_ack.cont
            if not content:
                return

            lines = content.split("\n")
            if not lines:
                return

            field_list = lines[0].split(",")
            value_list = lines[1:]  # 去掉第一行字段名

            self.m_field_list.clear()
            self.m_value_list.clear()

            self.m_field_list.extend(field_list)
            self.m_value_list.extend(value_list)

            self.transform_by_table(fetch_config_mod_ack, self.m_field_list, self.m_value_list)
