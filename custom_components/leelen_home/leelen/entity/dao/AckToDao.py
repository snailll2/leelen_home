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
from ...common.LeelenType import GatewayTable
from ...common.SingletonMixin import SingletonMixin
from ...handler.DeviceStatusEvent import DeviceStatusEvent
from ...handler import FlowRxBus
from ...models.LogicServerStateModel import LogicServerStateModel


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

    def transform_by_table(self, fetch_config_mod_ack, field_list: list[str], value_list: list[str]):
        """按表名分发到解析函数。无消费者的表直接跳过(增量无副作用)。"""
        tbl = fetch_config_mod_ack.tbl.lower()
        op_type = fetch_config_mod_ack.type

        LogUtils.i(f"获取table {tbl}数据 {op_type}")

        if tbl == GatewayTable.LOGIC_SERVER_STATE_TABLE_NAME.lower():
            self.trans_logic_server_state_data(field_list, value_list)

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