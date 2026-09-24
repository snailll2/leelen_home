"""网关增量配置 ack 的内容解析与状态事件派发。

原 Java 端口里这是「表数据落 Android 数据库」的 DAO 层;P1/P4 清理后
数据库逻辑已全部移除,真正存活的只有一条链路:

    transform_data() ← 每个 config fetch ack(LanDataResponseHandleModel)
      └ transform_by_table() 按表名分发
          └ trans_logic_server_state_data():解析 logic_server_state CSV,
            按去重规则发 DeviceStatusEvent → FlowRxBus(HA dispatcher 适配层)
            → 实体 update_state

其余表(device/device_state/logic_server/floor/scene...)的增量在此集成中
无消费者,已在 P1 时连同存储逻辑一并裁掉。
"""
import base64
import threading

from ...utils.LogUtils import LogUtils
from ...common.LeelenType import FunctionType, GatewayTable
from ...common.SingletonMixin import SingletonMixin
from ...handler.DeviceStatusEvent import DeviceStatusEvent
from ...handler import FlowRxBus
from ...models.LogicServerStateModel import LogicServerStateModel
from ...models.MsgStorageModel import MsgStorageModel


class AckToDao(SingletonMixin):
    TAG = "AckToDao"

    def __init__(self):
        self.m_value_list: list[str] = []
        self.m_field_list: list[str] = []
        # 同一 ack 内的串行解析;网关多包 ack 由 LAN 收包线程顺序投递,锁是防御性互斥
        self._lock = threading.Lock()

    def trans_logic_server_state_data(self, field_list, row_list):
        """解析 logic_server_state 表增量,按去重规则派发状态事件。

        行内字段:logic_addr, func_id, state(base64 编码的设备状态字节)。
        去重:func_id 在 {55318, 53268, 43029} 时,前后两次状态首字节都是 0
        视为「重复上报」不再重复发事件(这些功能位持续 0 时风暴抑制)。
        """
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
                    LogUtils.e(self.TAG, f"base64 state decode exception : {e}")
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

            if should_post_event:
                device_event = DeviceStatusEvent()
                device_event.logic_address = logic_addr
                device_event.function_id = func_id
                device_event.state = state_bytes
                FlowRxBus.post(device_event)

            device_state[func_id] = state_bytes
            model.add_or_update_state(logic_addr, device_state)

    def trans_msg_storage_data(self, field_list, row_list):
        """解析 msg_storage_common_tbl 电能行,合并缓存并向插座派发用电量事件。

        行内字段(与网关 CSV 表头一致):link_target_code(插座的逻辑地址)、
        rec_type(22556 小时 / 22557 日 / 22558 月)、rec_cont(base64 编码的
        6 字节累计计数)、rec_time("yyyy-MM-dd HH:mm:ss")。其余字段(str/state_flag/
        create_time...)不使用。

        合并后对每个出现过的 link_target_code 派发两个合成事件
        (function_id=22556/22557,state=b"")——真实 kWh 在实体侧的
        ``CommonModel.get_cur_state`` 里从 MsgStorageModel 即时计算
        (事件属性不足时置空,但 function_id/逻辑地址正是实体匹配依据)。
        """
        model = MsgStorageModel.get_instance()

        try:
            code_index = field_list.index("link_target_code")
            rec_type_index = field_list.index("rec_type")
            rec_time_index = field_list.index("rec_time")
            cont_index = field_list.index("rec_cont")
        except ValueError:
            # 表头缺电能字段(可能只有锁档等异构行),本次增量优雅跳过
            return

        energy_rec_types = {
            FunctionType.FUNCTION_SMART_SOCKET_HOUR_POWER,
            FunctionType.FUNCTION_SMART_SOCKET_DAY_POWER,
            FunctionType.FUNCTION_SMART_SOCKET_MONTH_POWER,
        }

        upserted_any = False
        for row in row_list:
            fields = row.split(',')
            if len(fields) != len(field_list):
                continue

            try:
                code = int(fields[code_index])
                rec_type = int(fields[rec_type_index])
                rec_time = fields[rec_time_index]
            except (ValueError, IndexError):
                continue

            if rec_type not in energy_rec_types:
                continue

            try:
                cont = base64.b64decode(fields[cont_index])
            except Exception as e:
                LogUtils.e(self.TAG, f"msg_storage rec_cont base64 decode exception : {e}")
                continue

            model.upsert(code, rec_type, rec_time, cont)
            upserted_any = True

        if not upserted_any:
            return

        # 只对「有过小时行」的插座派发今日/本月事件,避免无数据插座反复空转。
        for code in model.codes_with_data():
            if not model.has_type(code, FunctionType.FUNCTION_SMART_SOCKET_HOUR_POWER):
                continue
            for function_id in (
                FunctionType.FUNCTION_SMART_SOCKET_HOUR_POWER,
                FunctionType.FUNCTION_SMART_SOCKET_DAY_POWER,
            ):
                device_event = DeviceStatusEvent()
                device_event.logic_address = code
                device_event.function_id = function_id
                device_event.state = b""
                FlowRxBus.post(device_event)

    def transform_by_table(self, fetch_config_mod_ack, field_list: list[str], value_list: list[str]):
        """按表名分发到解析函数。无消费者的表直接跳过(增量无副作用)。"""
        tbl = fetch_config_mod_ack.tbl.lower()
        op_type = fetch_config_mod_ack.type

        LogUtils.i(f"获取table {tbl}数据 {op_type}")

        if tbl == GatewayTable.LOGIC_SERVER_STATE_TABLE_NAME.lower():
            self.trans_logic_server_state_data(field_list, value_list)
        elif tbl == GatewayTable.MSG_STORAGE_COMMON_TABLE_NAME.lower():
            self.trans_msg_storage_data(field_list, value_list)

    def transform_data(self, fetch_config_mod_ack):
        """网关配置 ack 的统一入口:首行为字段名,其余为 CSV 数据行。"""
        LogUtils.i(f"transform_data 数据 {fetch_config_mod_ack} ")

        with self._lock:  # 单例对象上的真实互斥,替代每次新建的假锁
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