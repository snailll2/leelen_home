from ..common import DeviceType
from ..entity.GatewayInfo import GatewayInfo
from ..entity.User import User
from ..protocols.DeviceControlLanProtocol import DeviceControlLanProtocol
from ..utils.ConvertUtils import ConvertUtils
from ..utils.TlvUtils import TlvUtils
from ..utils.LogUtils import LogUtils


class ControlModel:
    _instance = None

    def __init__(self):
        pass

    @classmethod
    def get_instance(cls) -> 'ControlModel':
        if not cls._instance:
            cls._instance = ControlModel()
        return cls._instance

    def device_control(self, service_id: int, control_type: int, control_data: bytes) -> int:
        from ..HeartbeatService import HeartbeatService

        protocol = DeviceControlLanProtocol.get_instance()
        service_addr = ConvertUtils.short_to_little_byte_array(service_id)
        protocol.set_service_address(service_addr)

        tlv_info = TlvUtils.get_tlv_encode(
            TlvUtils.tlv_encode([], control_type, control_data, len(control_data))
        )
        protocol.set_encode_tlv_info(tlv_info)

        request_data = protocol.get_request_data(
            ConvertUtils.get_long_address_by_type(DeviceType.APP,
                                                  User.get_instance().get_account_id()),
            GatewayInfo.get_instance().get_gateway_desc(),
            service_addr
        )
        HeartbeatService.get_instance().request(request_data)
        return ConvertUtils.to_int(protocol.frame_id)

    def control(self, lin_base_state: 'LinBaseState', i: int = 0):
        from ..common.CommonModel import CommonModel

        service_address = lin_base_state.get_service_address()
        service_type = lin_base_state.get_service_type()
        # FUNCTION_CENTER_AC
        function_id = CommonModel.get_instance().get_function_id_by_service_type(service_type, i)
        control_value = CommonModel.get_instance().get_control_value(service_type, lin_base_state, i)
        LogUtils.i((service_address, service_type, function_id, control_value))

        if control_value is not None:
            control_result = ControlModel.get_instance().device_control(service_address, function_id, control_value)
            # EventModel.get_instance().set_control_listener(control_result, lin_operation_listener)
        # else:
        #     result = LinOperationResult()
        #     result.set_code(2)
        #     lin_operation_listener.on_complete(result)
