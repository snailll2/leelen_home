from ..common import DeviceType
from ..common.SingletonMixin import SingletonMixin
from ..common.LeelenType import APCIType, DeviceMode, PassThroughType
from ..entity.GatewayInfo import GatewayInfo
from ..states.LinBaseState import LinBaseState
from ..entity.User import User
from ..protocols.AppDevicePassThroughLanProtocol import AppDevicePassThroughLanProtocol
from ..protocols.DeviceControlLanProtocol import DeviceControlLanProtocol
from ..protocols.DeviceHintLanProtocol import DeviceHintLanProtocol
from ..utils.ConvertUtils import ConvertUtils
from ..utils.TlvUtils import TlvUtils
from ..utils.LogUtils import LogUtils



class ControlModel(SingletonMixin):
    def __init__(self):
        pass

    def device_control(self, service_id: int, control_type: int, control_data: bytes) -> int:
        LogUtils.i(f"!!! device_control called: addr={service_id}, func={control_type}, data={control_data.hex()}")
        from ..HeartbeatService import HeartbeatService

        protocol = DeviceControlLanProtocol()
        service_addr = ConvertUtils.short_to_little_byte_array(service_id)
        protocol.set_service_address(service_addr)

        tlv_info = TlvUtils.get_tlv_encode(
            TlvUtils.tlv_encode([], control_type, control_data, len(control_data))
        )
        protocol.set_encode_tlv_info(tlv_info)

        request_data = protocol.get_request_data(
            ConvertUtils.get_long_address_by_type(DeviceType.APP,
                                                  User.get_instance().account_id),
            GatewayInfo.get_instance().gateway_desc,
            service_addr
        )
        HeartbeatService.get_instance().request(request_data)
        return ConvertUtils.to_int(protocol.frame_id)

    def device_hint(self, device_addr: int, mode: bytes = DeviceMode.MODE_FLASH) -> int:
        """向设备发「定位闪烁」提示(官方 App 设备定位按钮同款指令)。

        cmd = DEVICE_HINT([5, 2]),body = [mode][deviceAddr 小端 2B]。
        设备收到 MODE_FLASH(bytes([1])) 后指示灯闪烁约 30 秒 —— 闪烁本身由设备
        固件完成,此处仅发一条启动指令,不需要本端脚本反复发开/关帧。
        """
        LogUtils.i(f"!!! device_hint called: addr={device_addr}, mode={mode.hex()}")
        from ..HeartbeatService import HeartbeatService

        protocol = DeviceHintLanProtocol()
        addr_bytes = ConvertUtils.short_to_little_byte_array(device_addr)
        protocol.set_hint(mode, addr_bytes)

        request_data = protocol.get_request_data(
            ConvertUtils.get_long_address_by_type(DeviceType.APP,
                                                  User.get_instance().account_id),
            GatewayInfo.get_instance().gateway_desc,
            addr_bytes
        )
        HeartbeatService.get_instance().request(request_data)
        return ConvertUtils.to_int(protocol.frame_id)

    def write_private_property(self, service_id: int, property_id: bytes, value: bytes) -> int:
        """经 App 设备透传写一条**逻辑通道**私有属性(官方 AppDevicePassThrough 同款)。

        官方 App 改窗帘电机方向/重置行程都走这条指令(apk 逆向基类
        BaseManagerImpl.appDevicePassThrough),cmd = PASS_THROUGH_APP_DEVICE([1, 6]),
        body = ``[01 TA][len][0x64 写私有属性][property_id][val_len][val]``,
        目标地址是**逻辑通道地址**(电机可写属性 163 挂在 logic_addr,不是 dev_addr)。

        property_id 取自 ``PropertyId.CURTAIN_MOTOR``(bytes([1, 163]))等 2 字节常量;
        值字节语义由调用方定义(窗帘:方向 bit0 + 重置行程 bit1)。
        """
        LogUtils.i(f"!!! write_private_property called: logic_addr={service_id}, "
                   f"property_id={property_id.hex()}, value={value.hex()}")
        from ..HeartbeatService import HeartbeatService

        # [01][len][0x64][property_id][val_len][val];len = 本字节之后的剩余长度。
        payload = bytearray()
        payload.extend(PassThroughType.TA)
        payload.append(4 + len(value))
        payload.extend(APCIType.WRITE_PRIVATE_PROPERTY)
        payload.extend(property_id)
        payload.append(len(value))
        payload.extend(value)

        protocol = AppDevicePassThroughLanProtocol()
        protocol.set_payload_data(bytes(payload))
        service_addr = ConvertUtils.short_to_little_byte_array(service_id)

        request_data = protocol.get_request_data(
            ConvertUtils.get_long_address_by_type(DeviceType.APP,
                                                  User.get_instance().account_id),
            GatewayInfo.get_instance().gateway_desc,
            service_addr
        )
        HeartbeatService.get_instance().request(request_data)
        return ConvertUtils.to_int(protocol.frame_id)

    def control(self, lin_base_state: LinBaseState, i: int = 0):
        from ..common.CommonModel import CommonModel

        service_address = lin_base_state.get_service_address()
        service_type = lin_base_state.get_service_type()
        # FUNCTION_CENTER_AC
        function_id = CommonModel.get_instance().get_function_id_by_service_type(service_type, i)
        control_value = CommonModel.get_instance().get_control_value(service_type, lin_base_state, i)
        LogUtils.i((service_address, service_type, function_id, control_value))

        if control_value is not None:
            # 返回值(帧 id)当前无人消费,直接丢弃;调用本身有副作用(下发控制帧)
            ControlModel.get_instance().device_control(service_address, function_id, control_value)
        # else:
        #     result = LinOperationResult()
        #     result.set_code(2)
        #     lin_operation_listener.on_complete(result)