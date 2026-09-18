from threading import Lock
from typing import Optional
import logging

from ..utils.LogUtils import LogUtils
from .SingletonMixin import SingletonMixin
from ..common import FunctionValue, FunctionType
from ..common.LeelenType import LogicDeviceType
from ..models.DeviceStateModel import DeviceStateModel
from ..states.LinBaseState import LinBaseState
from ..states.LinCenterAcState import LinCenterAcState
from ..states.LinCurtainMotorState import LinCurtainMotorState
from ..states.LinSensorState import LinSensorState
from ..utils.ConvertUtils import ConvertUtils

_LOGGER = logging.getLogger(__name__)

# LeelenType 里没有为这几个值命名,就地起名并记录语义(取值保持不变)。
#: 开关型设备服务类型(灯/开关面板),2 与 3 走同一条解析路径。
SERVICE_TYPE_SWITCH = 2
SERVICE_TYPE_SWITCH_ALT = 3
#: 调光服务类型。
SERVICE_TYPE_DIMMER = 49
#: 地暖执行器的第二个功能号(51234 的另一变体,LeelenType 未命名)。
FUNCTION_FLOOR_ACTUATOR_ALT = 51235
#: 空调设定温度的编码范围:报文里以 0..14 表示 16..30℃,超出范围用 31 表示「沿用/无效」。
AC_TEMP_ENCODE_MIN = 16
AC_TEMP_ENCODE_MAX = 30
AC_TEMP_ENCODE_INVALID = 31
#: 空调风速/模式编码里的「无效值」占位。
AC_SPEED_ENCODE_INVALID = 7
AC_MODE_ENCODE_INVALID = 7
AC_MODE_ENCODE_MAX = 4
#: 解析空调上报时的兜底值(风速字段非法时按中风处理)。
AC_SPEED_PARSE_DEFAULT = 2
#: 默认设定温度(上报帧未给出温度时)。
AC_TEMP_DEFAULT = 26
#: 该服务类型上报即视为「开」(语义待真机确认;LeelenType 中 154 亦记作 TYPE_IPC)。
SERVICE_TYPE_IMPLIES_ON = 154


class CommonModel(SingletonMixin):
    def __init__(self):
        self._lock = Lock()
        # self.mDeviceModel =

    def get_function_id_by_service_type(self, service_type: int, param2: int) -> int:
        result = FunctionType.FUNCTION_ON_OFF  # 默认返回值

        if service_type in {SERVICE_TYPE_SWITCH, SERVICE_TYPE_SWITCH_ALT, SERVICE_TYPE_DIMMER,
                            LogicDeviceType.TYPE_WIRELESS_LIGHT,
                            LogicDeviceType.WIRELESS_OUT_PUT_SWITCH,
                            LogicDeviceType.ZIGBEE_SMART_WALL_SOCKET}:
            return result
        elif service_type in {LogicDeviceType.TYPE_FLOOR_HEATING_NEW,
                              LogicDeviceType.ZIGBEE_FLOOR_HEARTING}:
            return FunctionType.FUNCTION_FLOOR_HEATING
        elif service_type in {LogicDeviceType.TYPE_REFRESH_AIR,
                              LogicDeviceType.ZIGBEE_REFRESH_AIR,
                              LogicDeviceType.ZIGBEE_AC_GATEWAY_REFRESH_AIR,
                              LogicDeviceType.TYPE_VENTILATION_SYSTEM}:
            return FunctionType.FUNCTION_LEVEL_GEARS
        elif service_type == LogicDeviceType.ARM:
            return FunctionType.FUNCTION_ARM
        elif service_type == LogicDeviceType.TYPE_DIMMING_LIGHT_ZIGBEE:
            return FunctionType.FUNCTION_LEVEL_DIMMER
        elif service_type in {LogicDeviceType.TYPE_CURTAIN,
                              LogicDeviceType.TYPE_SHADE_CONTROLLER,
                              LogicDeviceType.TYPE_WIRELESS_CURTAIN,
                              LogicDeviceType.WIRELESS_OUT_PUT_CURTAIN,
                              LogicDeviceType.TYPE_WIRELESS_ROLL_CURTAIN,
                              LogicDeviceType.DREAM_CURTAIN}:
            return FunctionType.FUNCTION_CURTAIN
        elif service_type in {LogicDeviceType.ZIGBEE_AC_GATEWAY_AC,
                              LogicDeviceType.TYPE_CENTER_AIR_CONDITIONER}:
            if param2 == FunctionType.FUNCTION_CENTER_AC_ZH_GROUP:
                # FUNCTION_CENTER_AC_ZH
                return FunctionType.FUNCTION_CENTER_AC_ZH
            return FunctionType.FUNCTION_CENTER_AC
        elif service_type == LogicDeviceType.TYPE_BACK_AUDIO_BGM:
            return FunctionType.FUNCTION_MUSIC_ARG_CONTROL
        elif service_type in {LogicDeviceType.TYPE_AC_ACTUATOR, LogicDeviceType.DIY_CENTER_AC}:
            return FunctionType.FUNCTION_AC_ACTUATOR
        elif service_type in {LogicDeviceType.TYPE_FRESH_ACTUATOR, LogicDeviceType.DIY_REFRESH_AIR}:
            return FunctionType.FUNCTION_FRESH_ACTUATOR
        elif service_type in {LogicDeviceType.TYPE_FLOOR_ACTUATOR, LogicDeviceType.DIY_FLOOR_HEARTING}:
            return FunctionType.FUNCTION_FLOOR_ACTUATOR
        else:
            return result

    def get_control_value(self, control_type: int, state, mode: int) -> bytes:
        if control_type in {SERVICE_TYPE_SWITCH, SERVICE_TYPE_SWITCH_ALT,
                            LogicDeviceType.WIRELESS_OUT_PUT_CURTAIN,
                            LogicDeviceType.TYPE_AC_ACTUATOR,
                            LogicDeviceType.TYPE_FRESH_ACTUATOR,
                            LogicDeviceType.TYPE_FLOOR_ACTUATOR,
                            LogicDeviceType.DIY_CENTER_AC,
                            LogicDeviceType.DIY_FLOOR_HEARTING,
                            LogicDeviceType.DIY_REFRESH_AIR}:
            return self.get_switch_control_value(state)

        if control_type in {LogicDeviceType.TYPE_CENTER_AIR_CONDITIONER,
                            LogicDeviceType.ZIGBEE_SMART_WALL_SOCKET,
                            LogicDeviceType.TYPE_DIMMING_LIGHT_ZIGBEE,
                            LogicDeviceType.ZIGBEE_CENTER_AC,
                            LogicDeviceType.ZIGBEE_FLOOR_HEARTING,
                            LogicDeviceType.ZIGBEE_REFRESH_AIR}:
            return self.get_center_ac_control_value(state, mode)

        if control_type in {LogicDeviceType.TYPE_CURTAIN,
                            LogicDeviceType.TYPE_SHADE_CONTROLLER,
                            LogicDeviceType.TYPE_WIRELESS_LIGHT,
                            LogicDeviceType.WIRELESS_OUT_PUT_SWITCH}:
            return self.get_curtain_control_value(state)

        if control_type in {LogicDeviceType.TYPE_WIRELESS_CURTAIN,
                            LogicDeviceType.TYPE_WIRELESS_ROLL_CURTAIN,
                            LogicDeviceType.DREAM_CURTAIN,
                            LogicDeviceType.ZIGBEE_AC_GATEWAY_AC,
                            LogicDeviceType.ZIGBEE_AC_GATEWAY_REFRESH_AIR}:
            return self.get_curtain_motor_control_value(state)

        # 默认处理逻辑
        return self.get_switch_control_value(state)

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
            i2 = AC_TEMP_ENCODE_INVALID
            if AC_TEMP_ENCODE_MIN <= setting_temp <= AC_TEMP_ENCODE_MAX:
                i2 = setting_temp - AC_TEMP_ENCODE_MIN

            if param != FunctionType.FUNCTION_CENTER_AC_ZH_GROUP:
                i6 = mode if 0 <= mode <= AC_MODE_ENCODE_MAX else AC_MODE_ENCODE_INVALID
            else:
                i6 = mode

            i3 = speed if speed >= 1 else AC_SPEED_ENCODE_INVALID
            i4 = i6
            i5 = 3
        else:
            i2 = AC_TEMP_ENCODE_INVALID
            i3 = AC_SPEED_ENCODE_INVALID
            i4 = AC_MODE_ENCODE_INVALID

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
            # 状态字节由调用方经 logic_server_state 传入,原先按功能类型再查一次设备状态
            # 的步骤(见下方注释)已不再需要。
            # 原:logic_server_state = self.m_device_model.get_logic_server_state_by_address_and_function_type(i2, function_type)

            # 默认值初始化
            power = 1
            mode = 2
            speed = 3
            temp = AC_TEMP_DEFAULT  # 默认温度

            if logic_server_state and len(logic_server_state) >= 2:
                byte0 = logic_server_state[0]
                byte1 = logic_server_state[1]

                # 解析各字段
                sub_byte_val = ConvertUtils.sub_byte(byte0, 0, 5)  # 0-4位，共5位
                sub_byte2 = ConvertUtils.sub_byte(byte0, 5, 8)  # 5-7位，共3位
                sub_byte3 = ConvertUtils.sub_byte(byte1, 0, 3)  # 0-2位，共3位
                power = ConvertUtils.sub_byte(byte1, 3, 5)  # 3-4位，共2位

                # 温度计算
                temp_raw = sub_byte_val + AC_TEMP_ENCODE_MIN
                temp = min(temp_raw, AC_TEMP_ENCODE_MAX)  # 限制温度上限

                # 风速校验
                if (sub_byte2 < 1 or sub_byte2 > 3) and sub_byte2 != 5:
                    speed = AC_SPEED_PARSE_DEFAULT  # 无效值时设为默认
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
            power_state = 1 if is_on or i2 == SERVICE_TYPE_IMPLIES_ON else 0

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

    def get_cur_fresh_air_module_state(self, service_type: int, device_addr: int, state_bytes):
        """解析新风执行器状态（49185/774/780）"""
        with self._lock:
            power_state = 0
            if state_bytes and len(state_bytes) > 0:
                # 直接取第一个字节作为状态值，1=低风，2=中风，3=高风，0xFE=自动
                power_state = state_bytes[0]

            # 使用 LinCenterAcState 承载状态，因为新风和空调共用部分字段
            fresh_air_state = LinCenterAcState()
            fresh_air_state.set_power_state(power_state)  # 关键：将字节值赋给 power_state
            fresh_air_state.set_service_type(service_type)
            fresh_air_state.set_service_address(device_addr)
            # 把原始字节也保存一份，供 update_state 回退逻辑使用
            fresh_air_state.state = state_bytes
            return fresh_air_state

    def get_cur_floor_heating_state(self, device_addr, service_type, state_bytes):
        """解析地暖执行器状态（51234/51235/775/779）"""
        with self._lock:
            power_state = 0
            _LOGGER.info("!!! CommonModel floor heating: addr=%s, service_type=%s, raw_bytes=%s",
                          device_addr, service_type, state_bytes.hex() if state_bytes else None)
            if state_bytes and len(state_bytes) >= 2:
                # 第二个字节的 bit0 为开关状态：1=开，0=关
                power_state = state_bytes[1] & 0x01

            heating_state = LinCenterAcState()
            heating_state.set_power_state(power_state)
            heating_state.set_service_type(service_type)
            heating_state.set_service_address(device_addr)
            heating_state.state = state_bytes
            return heating_state
    
    def get_v_switch_state(self, device_addr, service_type, state_bytes):
        with self._lock:
            # state_bytes 定义
            # \x01\x00\x00\x00 为开
            # \x02\x00\x00\x00 为关
            # 关必须映射成 2(而不是 0):VSwitch 侧按 power_state in (1, 2) 判定这份上报
            # 是否携带有效状态,映射成 0 会被当成「未携带」而整条丢弃,导致关状态刷不出来。
            power_state = 0
            if state_bytes and len(state_bytes) == 4:
                if state_bytes[0] == 0x01:
                    power_state = 1
                elif state_bytes[0] == 0x02:
                    power_state = 2

            # 只在字节数足够时打印逐字节内容:原实现在 f-string 里无条件索引
            # state_bytes[0..3],None 或短包会抛 IndexError(f-string 在调用前求值,
            # 日志级别挡不住,而这里位于锁内且无 try)。
            if state_bytes and len(state_bytes) >= 4:
                LogUtils.d(
                    f"VSwitch: {device_addr}, {service_type}, {state_bytes.hex()}, "
                    f"power_state={power_state}, state_bytes[0..3] = "
                    f"{state_bytes[0]},{state_bytes[1]},{state_bytes[2]},{state_bytes[3]}"
                )
            else:
                LogUtils.d(
                    f"VSwitch: {device_addr}, {service_type}, "
                    f"state_bytes={state_bytes!r}, power_state={power_state}(长度不足,未解析)"
                )

            switch_state = LinBaseState()
            switch_state.set_power_state(power_state)
            switch_state.set_service_type(service_type)
            switch_state.set_service_address(device_addr)
            switch_state.state = state_bytes
            return switch_state
    


    def get_cur_state(self, device_addr, service_type, state_bytes):
        # 高优先级直接返回的情况

        if service_type in {FunctionType.FUNCTION_TEMPERATURE,
                            FunctionType.FUNCTION_HUMIDITY,
                            FunctionType.FUNCTION_PM,
                            FunctionType.FUNCTION_FORMALDEHYDE,
                            FunctionType.FUNCTION_CO,
                            FunctionType.FUNCTION_VOC,
                            FunctionType.FUNCTION_ILLUMINANCE,
                            FunctionType.FUNCTION_TYPE_HORIZONTAL}:
            return self.get_cur_sensor_state(device_addr, service_type, state_bytes)
        # 55334 FUNCTION_ARM , 16267  FUNCTION_ARM_CONDITION 为虚拟开关
        if service_type in {FunctionType.FUNCTION_ARM, FunctionType.FUNCTION_ARM_CONDITION}:
            return self.get_v_switch_state(device_addr, service_type, state_bytes)

        if service_type in {FunctionType.FUNCTION_AC_TEMP}:
            return self.get_cur_sensor_state(device_addr, service_type, state_bytes)

        if service_type in (SERVICE_TYPE_SWITCH, SERVICE_TYPE_SWITCH_ALT):
            return self.get_cur_switch_state(device_addr, service_type, state_bytes)

        # 分类处理
        if service_type in {LogicDeviceType.TYPE_CURTAIN,
                            LogicDeviceType.TYPE_SHADE_CONTROLLER,
                            LogicDeviceType.WIRELESS_OUT_PUT_CURTAIN}:
            return self.get_cur_curtain_state(device_addr)

        if service_type in {LogicDeviceType.TYPE_WIRELESS_ROLL_CURTAIN,
                            LogicDeviceType.TYPE_WIRELESS_CURTAIN,
                            FunctionType.FUNCTION_CURTAIN}:
            return self.get_cur_curtain_motor_state(device_addr, state_bytes)

        if service_type == LogicDeviceType.DREAM_CURTAIN:
            return self.get_dream_curtain_state(device_addr)

        if service_type in {LogicDeviceType.ZIGBEE_AC_GATEWAY_AC,
                            LogicDeviceType.TYPE_CENTER_AIR_CONDITIONER,
                            LogicDeviceType.ZIGBEE_CENTER_AC,
                            LogicDeviceType.TYPE_AC_ACTUATOR,
                            LogicDeviceType.DIY_CENTER_AC,
                            FunctionType.FUNCTION_CENTER_AC}:
            return self.get_cur_center_ac_state(service_type, device_addr, state_bytes)

        if service_type in {LogicDeviceType.ZIGBEE_AC_GATEWAY_REFRESH_AIR,
                            LogicDeviceType.TYPE_REFRESH_AIR,
                            LogicDeviceType.ZIGBEE_REFRESH_AIR,
                            LogicDeviceType.TYPE_FRESH_ACTUATOR,
                            LogicDeviceType.DIY_REFRESH_AIR,
                            FunctionType.FUNCTION_FRESH_ACTUATOR}:
            return self.get_cur_fresh_air_module_state(service_type, device_addr, state_bytes)

        if service_type in {SERVICE_TYPE_DIMMER,
                            LogicDeviceType.TYPE_DIMMING_LIGHT_ZIGBEE}:
            return self.get_cur_dimmer_state(service_type, device_addr)

        if service_type == LogicDeviceType.TYPE_VENTILATION_SYSTEM:
            return self.get_cur_ventilation_system_state(device_addr)

        # 地暖分支：包含原有类型及 51234, 51235
        if service_type in {LogicDeviceType.TYPE_FLOOR_HEATING_NEW,
                            LogicDeviceType.ZIGBEE_FLOOR_HEARTING,
                            LogicDeviceType.TYPE_FLOOR_ACTUATOR,
                            LogicDeviceType.DIY_FLOOR_HEARTING,
                            FunctionType.FUNCTION_FLOOR_ACTUATOR,
                            FUNCTION_FLOOR_ACTUATOR_ALT}:
            return self.get_cur_floor_heating_state(device_addr, service_type, state_bytes)

        if service_type == LogicDeviceType.LADDER_CONTROL:
            return self.get_cur_ladder_state(device_addr)

        if service_type == FunctionType.FUNCTION_POWER:
            return self.get_cur_sensor_power(device_addr, service_type, state_bytes)

        if service_type == LogicDeviceType.ZIGBEE_SMART_WALL_SOCKET:
            return self.get_cur_smart_socket_state(device_addr)

        if service_type in {LogicDeviceType.TYPE_RGB_TEMPERATURE_LIGHT,
                           LogicDeviceType.TYPE_COLOR_TEMPERATURE_LIGHT,
                           LogicDeviceType.TYPE_LIGHT_STRIP}:
            return self.get_cur_rgb_light_state(service_type, device_addr)

        # 默认情况：开关
        return self.get_cur_switch_state(device_addr, service_type, state_bytes)

    def get_cur_curtain_state(self, device_addr):
        """窗帘(58/59/571)。真机字节格式未确认,先返回兜底状态避免 AttributeError。待真机验证。"""
        return self._generic_fallback_state("curtain", device_addr)

    def get_dream_curtain_state(self, device_addr):
        """梦幻帘(574)。真机字节格式未确认,先返回兜底状态。待真机验证。"""
        return self._generic_fallback_state("dream_curtain", device_addr)

    def get_cur_dimmer_state(self, service_type, device_addr):
        """调光(49/561)。真机字节格式未确认,先返回兜底状态。待真机验证。"""
        return self._generic_fallback_state("dimmer", device_addr)

    def get_cur_ventilation_system_state(self, device_addr):
        """通风系统(148)。真机字节格式未确认,先返回兜底状态。待真机验证。"""
        return self._generic_fallback_state("ventilation", device_addr)

    def get_cur_ladder_state(self, device_addr):
        """阶梯(158)。真机字节格式未确认,先返回兜底状态。待真机验证。"""
        return self._generic_fallback_state("ladder", device_addr)

    def get_cur_smart_socket_state(self, device_addr):
        """智能插座(518)。真机字节格式未确认,先返回兜底状态。待真机验证。"""
        return self._generic_fallback_state("smart_socket", device_addr)

    def get_cur_rgb_light_state(self, service_type, device_addr):
        """RGB 灯(567/568/569)。真机字节格式未确认,先返回兜底状态。待真机验证。"""
        return self._generic_fallback_state("rgb_light", device_addr)

    def _generic_fallback_state(self, device_kind: str, service_address: int) -> LinBaseState:
        """兜底解析:可解析类型缺失时返回泛型状态,保证状态传递不中断。"""
        LogUtils.w(
            f"CommonModel: {device_kind}(addr={service_address}) 解析器未实现,"
            f"返回兜底状态 — 待真机验证该设备类型的字节格式"
        )
        state = LinBaseState()
        state.set_service_address(service_address)
        return state