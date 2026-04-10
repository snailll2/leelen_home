import logging
from typing import Dict

from ..utils.ConvertUtils import ConvertUtils

_LOGGER = logging.getLogger(__name__)

OUT_LINE = "--"


class DeviceStateModel:
    _instance = None

    def __init__(self):
        self._state_map: Dict[int, int] = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = DeviceStateModel()
        return cls._instance

    def add_or_update_device_state(self, address: int, state: int):
        _LOGGER.info(f"添加或更新设备状态，address = {address}；state = {state}")
        self._state_map[address] = state

    def delete_device_states(self):
        _LOGGER.info("删除当前网关所有物理设备状态")
        self._state_map.clear()

    def get_device_state_by_address(self, address: int) -> int:
        return self._state_map.get(address, 0)

    def _get_state_by_func(self, device_addr: int, logic_addr: int, data, func_id: int = 0, byte_len: int = 2):
        # if self.get_device_state_by_address(device_addr) != 0:
        #     data = LogicServerStateModel.get_instance().get_logic_server_state(logic_addr, func_id)

        if data:
            if len(data) == byte_len:
                if byte_len == 2:
                    return ConvertUtils.to_unsigned_short(data)
                if byte_len == 1:
                    return ConvertUtils.to_int(data)
            return ConvertUtils.to_int(data)

        return OUT_LINE
        
    def get_power_state(self, device_addr: int, logic_addr: int, data, func_id: int = 0):
        if data:
            return ConvertUtils.to_int(data)
        return OUT_LINE
    def get_co_state(self, device_addr: int, logic_addr: int, data):
        return self._get_state_by_func(device_addr, logic_addr, data, 18478)

    def get_formaldehyde_state(self, device_addr: int, logic_addr: int, data):
        return self._get_state_by_func(device_addr, logic_addr, data, 18479)

    def get_voc_state(self, device_addr: int, logic_addr: int, data):
        return self._get_state_by_func(device_addr, logic_addr, data, 18480)

    def get_humidity_state(self, device_addr: int, logic_addr: int, data):
        return self._get_state_by_func(device_addr, logic_addr, data, 16395, byte_len=1)

    def get_illuminance_state(self, device_addr: int, logic_addr: int, data):
        return self._get_state_by_func(device_addr, logic_addr, data, 18477)

    def get_pm_state(self, device_addr: int, logic_addr: int, data):
        # if self.get_device_state_by_address(device_addr) != 0:
        # data = LogicServerStateModel.get_instance().get_logic_server_state(logic_addr, 18455)
        if data and len(data) == 2:
            value = ConvertUtils.to_unsigned_short(data)
            if value <= 75:
                return f"优{value}"
            elif value <= 150:
                return f"良{value}"
            elif value <= 250:
                return f"中{value}"
            else:
                return f"差{value}"
        return OUT_LINE

    # return OUT_LINE

    def get_temperature_state(self, device_addr: int, logic_addr: int, data):
        # if self.get_device_state_by_address(device_addr) == 0:
        #     return OUT_LINE

        func_ids = [18442, 22529]
        for fid in func_ids:
            # data = LogicServerStateModel.get_instance().get_logic_server_state(logic_addr, fid)
            _LOGGER.debug(f"getTemperatureState() func {fid} is None: {data is None}")
            if data and len(data) == 2:
                high = data[1]
                low = data[0]
                if high < 0:
                    high += 256
                temp_val = ((high * 100) + low) / 100.0 - 100.0
                return round(float(temp_val), 1)

        return OUT_LINE

    def update_device_state_by_address(self, device_addr: int, state: int):
        _LOGGER.info(f"更新设备状态，deviceAddress = {device_addr}；state = {state}")
        self._state_map[device_addr] = state

        # event = DeviceStatusUpdateEvent()
        # event.device_address = device_addr
        # event.is_online = state == 1
        # RxBus.get_instance().post(event)

    def get_environment_state_val(self, index: int, device_addr: int, logic_addr: int, data):
        if index == 0:
            return self.get_pm_state(device_addr, logic_addr, data)
        elif index in {18442, 22529}:
            return self.get_temperature_state(device_addr, logic_addr, data)
        elif index == 16395:
            return self.get_humidity_state(device_addr, logic_addr, data)
        elif index == 18479:
            return self.get_formaldehyde_state(device_addr, logic_addr, data)
        elif index == 18478:
            return self.get_co_state(device_addr, logic_addr, data)
        elif index == 18480:
            return self.get_voc_state(device_addr, logic_addr, data)
        elif index == 18477:
            return self.get_illuminance_state(device_addr, logic_addr, data)
        # 功率
        elif index == 20517:
            return self.get_power_state(device_addr, logic_addr, data)
        else:
            return self._get_state_by_func(device_addr, logic_addr, data)
