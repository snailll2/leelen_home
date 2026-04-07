from collections import defaultdict
from threading import Lock

from ..handler.DeviceStatusEvent import DeviceStatusEvent
from ..handler.FlowRxBus import FlowRxBus
from ..utils.LogUtils import LogUtils


class LogicServerStateModel:
    TAG = "🍋 LogicServerStateModel"
    _instance = None
    _lock = Lock()

    def __init__(self):
        self.state_array = defaultdict(dict)
        pass

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = cls()
        return cls._instance

    def add_or_update_state(self, logic_address: int, state_dict: dict[int, bytes]):
        LogUtils.i(self.TAG, f"添加或更新逻辑设备状态，address = {logic_address} {state_dict}")
        self.state_array[logic_address] = state_dict

    def delete_logic_server_state(self, logic_address):
        LogUtils.d(f"{self.TAG}: 删除单条逻辑服务状态，logicAddress = {logic_address}")

    def delete_logic_server_states(self):
        LogUtils.d(f"{self.TAG}: 删除当前网关所有逻辑设备状态")

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
        FlowRxBus.get_instance().post(device_status)

        # # 发送环境状态事件
        env_function_ids = [18442, 22529, 16395, 18455, 18479, 18478, 18480, 18477]
        # if function_id in env_function_ids:
        #     env_status = EnvironmentStatusEvent()
        #     env_status.logic_address = logic_address
        #     env_status.function_id = function_id
        #     FlowRxBus.get_instance().post(env_status)

    def get_array_by_address(self, var1):
        return self.state_array.get(var1)
