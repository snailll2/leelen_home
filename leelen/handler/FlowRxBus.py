import threading

from ..HeartbeatService import HeartbeatService
from ..common import FunctionValue
from ..common.CommonModel import CommonModel
from ..handler.DeviceStatusEvent import DeviceStatusEvent
from ..utils.ConvertUtils import ConvertUtils
from ..utils.LogUtils import LogUtils
from ... import DOMAIN
from ..common.LeelenType import *

class FlowRxBus:
    MSG_TYPE_LOGON_TIMEOUT = 3
    SOURCE_DEST_LENGTH = 8
    _instance = None
    _lock = threading.Lock()
    TAG = "🍅 FlowRxBus"

    def __init__(self):
        self._hass = None
        self.device_list = []

    @classmethod
    def get_instance(cls) -> 'FlowRxBus':
        with cls._lock:
            if not cls._instance:
                cls._instance = FlowRxBus()
            return cls._instance

    #
    # def get_hass_service_by_function_id(self, function_id, function_value):
    #     if function_id == FunctionType.FUNCTION_ON_OFF:
    #         if function_value == FunctionValue.VALUE_OFF:
    #             return SERVICE_TURN_OFF, {}
    #         if function_value == FunctionValue.VALUE_ON:
    #             return SERVICE_TURN_ON, {}



    def post(self, event: DeviceStatusEvent):

        logic_address = event.logic_address
        function_name = ""
        logic_name = ""
        # for device in self.device_list:
        #     if device["logic_addr"] == event.logic_address:
        #         # LogUtils.d(device["logic_name"])
        #         logic_name = device["logic_name"]

        # for function_value_name, function_value in FunctionValue.__dict__.items():
        #     if event.state == function_value:
        #         LogUtils.d(
        #             f"{self.TAG}: 更新指定逻辑地址的状态，logicAddress = {logic_address} {logic_name}；functionId = {event.function_id} {function_name};var3 = {event.state.hex()} {function_value_name}")

        for function_type_name, function_type_id in FunctionType.__dict__.items():
            if function_type_id == event.function_id:
                function_name = function_type_name
                break
        # LogUtils.d(
        #     f"{self.TAG}: 更新指定逻辑地址的状态，logicAddress = {logic_address}；functionId = {event.function_id} {function_type_name}；var3 = {event.state.hex()}")

        self._hass = HeartbeatService.get_instance().hass

        async def async_operation(logic_address, event):
            # service, service_data = self.get_hass_service_by_function_id(event.function_id, event.state)
            # service_data.update({ATTR_ENTITY_ID: f"leelen_logic_addr_{logic_address}"})
            # await self._hass.services.async_call(
            #     domain=DOMAIN, service=service, service_data=service_data
            # )
            unique_id = f"leelen_logic_addr_{logic_address}"
            entity = self._hass.data[DOMAIN]["entities"].get(unique_id)
            state = CommonModel.get_instance().get_cur_state(logic_address, event.function_id, event.state)
            state.set_service_type(event.function_id)
            state.set_service_address(logic_address)
            if entity:
                LogUtils.i(self.TAG,f"found entity {entity._name} {entity._device_name} {entity.entity_id} {entity.unique_id} {function_name} {state.__dict__} ")
                await entity.update_state(state)
                entity.async_write_ha_state()
            else:
                LogUtils.w(self.TAG,f"entity {unique_id} {function_name} not found ")

        
        if self._hass:
            self._hass.add_job(async_operation, logic_address, event)
