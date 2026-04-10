from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TlvInfo:
    type: int = 0
    len: int = 0
    value: bytes = b''


class TlvUtils:
    @staticmethod
    def get_comp_byte(b1: int, b2: int) -> int:
        return (b1 << 4) | b2

    @staticmethod
    def get_hig_byte(b: int) -> int:
        return (b & 0xF0) >> 4

    @staticmethod
    def get_low_byte(b: int) -> int:
        return b & 0x0F

    @staticmethod
    def get_tlv_encode(tlv_list: List[TlvInfo]) -> Optional[bytes]:
        if not tlv_list:
            return None

        # 计算总长度
        total_len = 0
        for tlv in tlv_list:
            if tlv.type <= 12:
                total_len += 1
            elif tlv.type <= 268:
                total_len += 2
            elif tlv.type <= 65804:
                total_len += 3
            else:
                return None

            total_len += tlv.len
            if tlv.len <= 12:
                pass
            elif tlv.len <= 268:
                total_len += 1
            elif tlv.len <= 65804:
                total_len += 2

        result = bytearray(total_len)
        pos = 0

        for tlv in tlv_list:
            t_type = tlv.type
            t_len = tlv.len

            # 处理type
            if t_type <= 12:
                t_byte = t_type
                t_extra = 0
            elif t_type <= 268:
                result[pos + 1] = t_type - 13
                t_byte = 13
                t_extra = 1
            elif t_type <= 65804:
                result[pos + 1] = (t_type - 269) >> 8
                result[pos + 2] = (t_type - 269) & 0xFF
                t_byte = 14
                t_extra = 2
            else:
                return None

            # 处理length
            if t_len <= 12:
                l_byte = t_len
                l_extra = 0
            elif t_len <= 268:
                result[pos + t_extra + 1] = t_len - 13
                l_byte = 13
                l_extra = 1
            elif t_len <= 65804:
                result[pos + t_extra + 1] = (t_len - 269) >> 8
                result[pos + t_extra + 2] = (t_len - 269) & 0xFF
                l_byte = 14
                l_extra = 2
            else:
                return None

            result[pos] = TlvUtils.get_comp_byte(t_byte, l_byte)
            value_pos = pos + 1 + t_extra + l_extra
            result[value_pos:value_pos + tlv.len] = tlv.value
            pos = value_pos + tlv.len

        return bytes(result)

    @staticmethod
    def tlv_decode(data: bytes, length: int) -> Optional[List[TlvInfo]]:
        result = []
        pos = 0

        while pos < length:
            t_byte = TlvUtils.get_hig_byte(data[pos])
            l_byte = TlvUtils.get_low_byte(data[pos])
            tlv = TlvInfo()

            # 处理type
            if t_byte <= 12:
                tlv.type = t_byte
                t_extra = 0
            elif t_byte == 13:
                tlv.type = (data[pos + 1] & 0xFF) + 13
                t_extra = 1
            elif t_byte == 14:
                tlv.type = ((data[pos + 1] << 8) & 0xFFFF) + 269 + (data[pos + 2] & 0xFF)
                t_extra = 2
            else:
                return None

            # 处理length
            if l_byte <= 12:
                tlv.len = l_byte
                l_extra = 0
            elif l_byte == 13:
                tlv.len = (data[pos + 1 + t_extra] & 0xFF) + 13
                l_extra = 1
            elif l_byte == 14:
                tlv.len = ((data[pos + 1 + t_extra] << 8) & 0xFFFF) + 269 + (data[pos + 2 + t_extra] & 0xFF)
                l_extra = 2
            else:
                return None

            value_pos = pos + 1 + t_extra + l_extra
            tlv.value = data[value_pos:value_pos + tlv.len]
            pos = value_pos + tlv.len
            result.append(tlv)

        return result

    @staticmethod
    def tlv_encode(tlv_list: List[TlvInfo], tlv_type: int, data: bytes, length: int) -> List[TlvInfo]:
        tlv = TlvInfo()
        tlv.type = tlv_type
        tlv.len = length
        tlv.value = data[:length]
        tlv_list.append(tlv)
        return tlv_list
