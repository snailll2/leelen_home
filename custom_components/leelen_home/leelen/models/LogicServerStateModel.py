from collections import defaultdict

from ..handler.DeviceStatusEvent import DeviceStatusEvent
from ..handler import FlowRxBus
from ..common.SingletonMixin import SingletonMixin
from ..utils.LogUtils import LogUtils

class LogicServerStateModel(SingletonMixin):
    TAG = "🍋 LogicServerStateModel"

    def __init__(self):
        self.state_array = defaultdict(dict)
        pass

    def add_or_update_state(self, logic_address: int, state_dict: dict[int, bytes]):
        LogUtils.i(self.TAG, f"添加或更新逻辑设备状态，address = {logic_address} {state_dict}")
        self.state_array[logic_address] = state_dict

    def update_device_state_by_device_address(self, logic_address, function_id, state_bytes):
        LogUtils.i(self.TAG,
            f"更新指定逻辑地址的状态，logicAddress = {logic_address}；functionId = {function_id}；var3 = {state_bytes}")

        # state = CommonModel.get_instance().get_cur_state(logic_address, function_id, state_bytes)
        # LogUtils.e(state)

        # 发送设备状态事件
        device_status = DeviceStatusEvent()
        device_status.logic_address = logic_address
        device_status.function_id = function_id
        device_status.state = state_bytes
        FlowRxBus.post(device_status)

        # # 发送环境状态事件(未移植:原先只对下列功能号额外发 EnvironmentStatusEvent)
        # # 环境类功能号:18442 温度 / 22529 空调温度 / 16395 湿度 / 18455 PM /
        # # 18479 甲醛 / 18478 CO / 18480 VOC / 18477 光照
        # if function_id in {18442, 22529, 16395, 18455, 18479, 18478, 18480, 18477}:
        #     env_status = EnvironmentStatusEvent()
        #     env_status.logic_address = logic_address
        #     env_status.function_id = function_id
        #     FlowRxBus.get_instance().post(env_status)

    def get_array_by_address(self, var1):
        return self.state_array.get(var1)
