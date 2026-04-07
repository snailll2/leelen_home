from threading import Lock
from typing import Optional

from ..utils.LogUtils import LogUtils
from ..common import FunctionValue
from ..models.DeviceStateModel import DeviceStateModel
from ..states.LinBaseState import LinBaseState
from ..states.LinCenterAcState import LinCenterAcState
from ..states.LinCurtainMotorState import LinCurtainMotorState
from ..states.LinSensorState import LinSensorState
from ..utils.ConvertUtils import ConvertUtils


class CommonModel:
    _instance = None

    def __init__(self):
        self._lock = Lock()
        # self.mDeviceModel =

    @staticmethod
    def get_instance():
        if CommonModel._instance is None:
            CommonModel._instance = CommonModel()
        return CommonModel._instance

    def get_function_id_by_service_type(self, service_type: int, param2: int) -> int:
        result = 51201  # 默认返回值

        if service_type in {2, 3, 49, 514, 515, 518}:
            return result
        elif service_type in {150, 662}:
            return 51213
        elif service_type in {152, 664, 783, 148}:
            return 49156
        elif service_type == 259:
            return 55334
        elif service_type == 561:
            return 51203
        elif service_type in {58, 59, 570, 571, 573, 574}:
            return 51202
        elif service_type in {782, 146}:
            if param2 == 2339:
                # FUNCTION_CENTER_AC_ZH
                return 51256
            return 55297
        elif service_type == 147:
            return 53268
        elif service_type in {773, 778}:
            return 51232
        elif service_type in {774, 780}:
            return 49185
        elif service_type in {775, 779}:
            return 51234
        else:
            return result

    def get_control_value(self, control_type: int, state, mode: int) -> bytes:
        if control_type in {2, 3, 571, 773, 774, 775, 778, 779, 780}:
            return self.get_switch_control_value(state)

        # if control_type == 49:
        #     return self.get_dimmer_control_value(state)
        #
        # if control_type == 150:
        #     return self.get_floor_heating_control_value(state)
        #
        # if control_type == 152:
        #     return self.get_fresh_air_module_control_value(state)
        #
        # if control_type == 259:
        #     return self.get_arm_control_value(state)

        if control_type in {146, 518, 561, 658, 662, 664}:
            return self.get_center_ac_control_value(state, mode)

        if control_type in {58, 59, 514, 515}:
            return self.get_curtain_control_value(state)

        if control_type in {570, 573, 574, 782, 783}:
            return self.get_curtain_motor_control_value(state)

        # if control_type == 147:
        #     return self.get_bgm_control_value(state)
        #
        # if control_type == 148:
        #     return self.get_fresh_air_control_value(state)
        #
        # if control_type in {566, 567, 568, 569}:
        #     return self.get_rgb_light_control_value(state)

        # 默认处理逻辑
        return self.get_switch_control_value(state)

    # def get_control_value(self, service_type: int, state, sub_type: int) -> bytes | None:
    #     if service_type in {2, 3, 49, 152, 514, 515, 664}:
    #         return self.get_switch_control_value(state)
    #     elif service_type in {658, 146, 782, 783}:
    #         return self.get_center_ac_control_value(state, sub_type)
    #     elif service_type in {58, 59, 570, 571, 573, 574}:
    #         return self.get_curtain_control_value(state)
    #     else:
    #         return self.get_switch_control_value(state)

    def get_switch_control_value(self, state) -> bytes | None:
        power_state = state.get_power_state()
        if power_state == 1:
            return FunctionValue.VALUE_ON
        elif power_state == 0:
            return FunctionValue.VALUE_OFF
        return None

    def get_center_ac_control_value(self, state, param: int) -> bytes:
        power_state = state.get_power_state()
        setting_temp = state.get_setting_temperature()
        mode = state.get_mode()
        speed = state.get_speed()

        i5 = 1 if power_state == 1 else 0

        if power_state not in (0, 1):
            i2 = 31
            if 16 <= setting_temp <= 30:
                i2 = setting_temp - 16

            if param != 2339:
                i6 = mode if 0 <= mode <= 4 else 7
            else:
                i6 = mode

            i3 = speed if speed >= 1 else 7
            i4 = i6
            i5 = 3
        else:
            i2 = 31
            i3 = 7
            i4 = 7

        value = (i5 << 11) + (i4 << 8) + (i3 << 5) + i2
        LogUtils.i(f"get_center_ac_control_value ===>{state}  {value}")
        return ConvertUtils.to_bytes(int(value))

    def get_curtain_control_value(self, lin_base_state: LinBaseState) -> bytes | None:
        power_state = lin_base_state.get_power_state()
        if power_state == 2:
            return FunctionValue.VALUE_CURTAIN_STOP
        elif power_state == 1:
            return FunctionValue.VALUE_CURTAIN_OPEN
        elif power_state == 0:
            return FunctionValue.VALUE_CURTAIN_CLOSE
        return None

    def get_curtain_motor_control_value(self, state) -> Optional[bytes]:
        if not isinstance(state, LinCurtainMotorState):
            return None

        power_state = state.get_power_state()

        if power_state == 0:
            return FunctionValue.VALUE_CURTAIN_CLOSE
        elif power_state == 1:
            return FunctionValue.VALUE_CURTAIN_OPEN
        elif power_state == 2:
            return FunctionValue.VALUE_CURTAIN_STOP
        elif power_state == 3:
            progress = state.get_progress()
            return bytes([progress, 0])
        else:
            return None

    def get_cur_center_ac_state(self, i, i2, logic_server_state):
        with self._lock:
            # 确定功能类型
            function_type = 51232 if i in (773, 778) else 55297
            # 获取设备状态字节
            # logic_server_state = self.m_device_model.get_logic_server_state_by_address_and_function_type(i2, function_type)

            # 默认值初始化
            power = 1
            mode = 2
            speed = 3
            temp = 26  # 默认温度

            if logic_server_state and len(logic_server_state) >= 2:
                byte0 = logic_server_state[0]
                byte1 = logic_server_state[1]

                # 解析各字段
                sub_byte_val = ConvertUtils.sub_byte(byte0, 0, 5)  # 0-4位，共5位
                sub_byte2 = ConvertUtils.sub_byte(byte0, 5, 8)  # 5-7位，共3位
                sub_byte3 = ConvertUtils.sub_byte(byte1, 0, 3)  # 0-2位，共3位
                power = ConvertUtils.sub_byte(byte1, 3, 5)  # 3-4位，共2位

                # 温度计算
                temp_raw = sub_byte_val + 16
                temp = min(temp_raw, 30)  # 限制温度上限

                # 风速校验
                if (sub_byte2 < 1 or sub_byte2 > 3) and sub_byte2 != 5:
                    speed = 2  # 无效值时设为默认
                else:
                    speed = sub_byte2

                # 模式直接赋值
                mode = sub_byte3

            # 创建空调状态对象
            ac_state = LinCenterAcState()
            ac_state.set_power_state(power)
            ac_state.set_mode(mode)
            ac_state.set_speed(speed)
            ac_state.set_setting_temperature(temp)

            return ac_state

    def get_cur_switch_state(self, i, i2, state_bytes):
        with self._lock:
            # state_bytes = self.mDeviceModel.get_logic_server_state_by_address_and_function_type(i, 51201)
            is_on = (
                    state_bytes is not None
                    and state_bytes == FunctionValue.VALUE_ON
            )
            power_state = 1 if is_on or i2 == 154 else 0

            light_state = LinBaseState()
            light_state.set_power_state(power_state)
            return light_state

    def get_cur_sensor_state(self, device_addr, service_type, state_bytes):
        with self._lock:
            value = DeviceStateModel.get_instance().get_environment_state_val(service_type, device_addr, device_addr, state_bytes)
            sensor_state = LinSensorState()
            sensor_state.set_value(value)
            return sensor_state
    
    def get_cur_sensor_power(self, device_addr, service_type, state_bytes):
        with self._lock:
            value = DeviceStateModel.get_instance().get_environment_state_val(service_type, device_addr, device_addr, state_bytes)
            sensor_state = LinSensorState()
            sensor_state.set_power(value)
            return sensor_state

    def get_cur_curtain_motor_state(self, address: int, state_bytes) -> LinCurtainMotorState:
        with self._lock:
            # state_bytes = self.mDeviceModel.get_logic_server_state_by_address_and_function_type(address, 51202)
            power_state = 1
            progress = 100  # 默认值

            if state_bytes:
                try:
                    mode = ConvertUtils.to_unsigned_short(state_bytes) >> 12
                    raw_progress = state_bytes[0]

                    if mode == 1:
                        progress = 1
                        power_state = 1
                    elif mode == 2:
                        progress = 1
                        power_state = 0
                    else:
                        progress = 0
                        power_state = 1 if raw_progress > 0 else 0

                    # 修正有效范围
                    if 0 <= raw_progress <= 100:
                        progress = raw_progress
                    else:
                        progress = -1

                except Exception as e:
                    raise RuntimeError(f"Failed to parse curtain motor state: {e}")

            result = LinCurtainMotorState()
            result.set_power_state(power_state)
            result.set_progress(progress)
            return result

    def get_cur_state(self, device_addr, service_type, state_bytes):
        # 高优先级直接返回的情况

        if service_type in {18442, 16395, 18455, 18479, 18478, 18480, 18477, 18304}:
            return self.get_cur_sensor_state(device_addr, service_type, state_bytes)

        if service_type in {22529}:
            return self.get_cur_sensor_state(device_addr, service_type, state_bytes)

        if service_type in (2, 3):
            return self.get_cur_switch_state(device_addr, service_type)

        # 分类处理
        if service_type in {58, 59, 571}:
            return self.get_cur_curtain_state(device_addr)

        if service_type in {573, 570, 51202}:
            return self.get_cur_curtain_motor_state(device_addr, state_bytes)

        if service_type == 574:
            return self.get_dream_curtain_state(device_addr)

        if service_type in {782, 146, 658, 773, 778, 55297}:
            return self.get_cur_center_ac_state(service_type, device_addr, state_bytes)

        if service_type in {783, 152, 664, 774, 780}:
            return self.get_cur_fresh_air_module_state(service_type, device_addr)

        if service_type in {49, 561}:
            return self.get_cur_dimmer_state(service_type, device_addr)

        if service_type == 148:
            return self.get_cur_ventilation_system_state(device_addr)

        if service_type in {150, 662, 775, 779}:
            return self.get_cur_floor_heating_state(device_addr, service_type)

        if service_type == 158:
            return self.get_cur_ladder_state(device_addr)
        
        if service_type == 20517:
            return self.get_cur_sensor_power(device_addr, service_type, state_bytes)


        if service_type == 518:
            return self.get_cur_smart_socket_state(device_addr)

        if service_type in {567, 568, 569}:
            return self.get_cur_rgb_light_state(service_type, device_addr)

        # 默认情况：开关
        return self.get_cur_switch_state(device_addr, service_type, state_bytes)
