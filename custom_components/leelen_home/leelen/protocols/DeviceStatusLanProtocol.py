import threading

from ..common import LanProtocolCmd
from ..models.LogicServerStateModel import LogicServerStateModel
from ..protocols.BaseLanProtocol import BaseLanProtocol
from ..utils.ConvertUtils import ConvertUtils
from ..utils.LogUtils import LogUtils
from ..utils.TlvUtils import TlvUtils


class DeviceStatusLanProtocol(BaseLanProtocol):
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        super().__init__()
        self.cmd = LanProtocolCmd.DEV_STATUS
        self.payload_type = bytes([0])

    @classmethod
    def get_instance(cls) -> 'DeviceStatusLanProtocol':
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = DeviceStatusLanProtocol()
        return cls._instance

    # def update_device_local_status(self, var1: bytes, var2: bytes, var3: bytes) -> None:
    def update_device_local_status(self, b_arr: bytes, b_arr2: bytes, b_arr3: bytes):
        if not b_arr2:
            LogUtils.i(self.TAG, "tlvData empty")
            return

        tlv_list = TlvUtils.tlv_decode(b_arr2, len(b_arr2))
        if not tlv_list:
            LogUtils.i(self.TAG, "tlvList is empty")
            return

        # 模拟 Java ByteBuffer.allocate(4) + put(bArr3) + put([0, 0])
        bb = bytearray(4)
        bb[0:len(b_arr3)] = b_arr3
        bb[2:] = b'\x00\x00'  # 最后两位补 0

        i = ConvertUtils.to_int(bb) + b_arr[0]

        for tlv in tlv_list:
            t = tlv.type
            if t in (16401, 47112):
                if t == 16401:
                    pass
                    # event = AcConnectNumAckEvent()
                    # event.address = i
                    # event.connect_data = tlv.value
                    # RxBus.get_instance().post(event)
                elif t == 47112:
                    pass
                    # event = IrLearnEvent()
                    # event.address = i
                    # event.is_success = (tlv.value[0] == 1)
                    # RxBus.get_instance().post(event)
            elif t != 51203 or (ConvertUtils.to_unsigned_short(tlv.value) >> 12) == 0:
                # LogUtils.d(f"---->update_device_state_by_device_address {(i, tlv.type, tlv.value)}")
                LogicServerStateModel.get_instance().update_device_state_by_device_address(i, tlv.type, tlv.value)

    def update_device_status(self, base_lan_protocol: BaseLanProtocol) -> None:
        b_arr = bytearray(1)
        b_arr2 = bytearray(1)
        b_arr3 = base_lan_protocol.request_data_body  # type: bytes
        length = len(b_arr3)
        wrap = memoryview(b_arr3)
        offset = 0
        b_arr4 = base_lan_protocol.device_source  # type: bytes

        while length - offset > 2:
            b_arr[0] = wrap[offset]
            offset += 1
            b_arr2[0] = wrap[offset]
            offset += 1

            i = b_arr2[0]
            if length - offset < i:
                return

            b_arr5 = wrap[offset:offset + i].tobytes()
            offset += i

            self.update_device_local_status(b_arr, b_arr5, b_arr4)
