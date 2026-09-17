import struct
from typing import List, Optional, Union

from .LogUtils import LogUtils

class ConvertUtils:
    DEFAULT_BYTEORDER = 'little'

    @staticmethod
    def byte_array_to_utf8_string(byte_array: bytes) -> str:
        try:
            return byte_array.decode('utf-8')
        except UnicodeDecodeError:
            return ""

    @staticmethod
    def bytes_to_ip(byte_array: bytes) -> str:
        return f"{byte_array[0]}.{byte_array[1]}.{byte_array[2]}.{byte_array[3]}"

    @staticmethod
    def bytes_to_mac(byte_array: bytes) -> str:
        return ":".join(f"{byte:02x}" for byte in byte_array)

    @staticmethod
    def get_32_bit_bin_string(number: int) -> str:
        return f"{number:032b}"

    @staticmethod
    def get_unsigned_int(number: int) -> int:
        return number & 0xFFFFFFFF

    @staticmethod
    def get_unsigned_short(number: int) -> int:
        return number & 0xFFFF

    @staticmethod
    def sub_bytes(byte_array: bytes, start: int, length: int) -> bytes:
        return byte_array[start:start + length]

    @staticmethod
    def bytes_to_hex(byte_array: Optional[bytes], separator: str = '') -> str:
        if byte_array is None:
            return ""
        return separator.join(f"{byte:02x}" for byte in byte_array)

    @staticmethod
    def get_address_by_type(device_type: str, address: int, byteorder: str = DEFAULT_BYTEORDER) -> bytes:
        if device_type is None or len(device_type) != 4:
            raise ValueError("parameter 'deviceType' invalid.")

        buffer = bytearray(8)
        struct.pack_into('Q', buffer, 0, address)
        if byteorder == 'little':
            buffer[6:8] = int(device_type, 16).to_bytes(2, byteorder)
        else:
            buffer[0:2] = int(device_type, 16).to_bytes(2, byteorder)
        return bytes(buffer)

    @staticmethod
    def get_desc_address_by_type(device_type: bytes, address: bytes) -> bytes:
        if device_type is None or len(device_type) != 2:
            raise ValueError("parameter 'deviceType' invalid.")

        buffer = bytearray(8)
        buffer[0:2] = device_type
        buffer[2:8] = address
        return bytes(reversed(buffer))

    @staticmethod
    def get_long_address_by_type(device_type: bytes, value: int) -> bytes:
        if device_type is None or len(device_type) != 2:
            raise ValueError("parameter 'deviceType' invalid.")
        # 将 long 值转换为 8 字节表示（按默认字节序）
        long_bytes = value.to_bytes(8, byteorder='little')
        # 用后 2 字节替换为 device_type（与 Java 中 position(6).put(bArr) 一致）
        long_address = bytearray(long_bytes)
        long_address[6:8] = device_type

        LogUtils.i("get_long_address_by_type", long_address.hex())

        return bytes(long_address)

    # @staticmethod
    # def hex_to_bytes(hex_string: str, byteorder: str = DEFAULT_BYTEORDER) -> bytes:
    #     if not hex_string or len(hex_string) % 2 != 0:
    #         return None
    #
    #     byte_array = bytearray.fromhex(hex_string)
    #     if byteorder == 'little':
    #         byte_array.reverse()
    #     return bytes(byte_array)
    @staticmethod
    def hex_to_bytes(hex_str: str, byte_order: str = 'big') -> bytes:
        if not hex_str or len(hex_str) % 2 != 0:
            return None

        num_bytes = len(hex_str) // 2
        byte_list = []

        if byte_order.lower() == 'little':
            # 大端：从末尾开始取
            for i in range(num_bytes):
                pos = len(hex_str) - (i + 1) * 2
                byte_list.append(int(hex_str[pos:pos + 2], 16))
        else:
            # 小端：从头开始取
            for i in range(num_bytes):
                pos = i * 2
                byte_list.append(int(hex_str[pos:pos + 2], 16))
        return bytes(byte_list)

    @staticmethod
    def hex_to_bytes2(hex_str: str, byte_order: str = 'big') -> bytes:
        # 与 hex_to_bytes 完全等价,统一走前者。
        return ConvertUtils.hex_to_bytes(hex_str, byte_order)

    @staticmethod
    def int_to_little_byte_array(number: int) -> bytes:
        return number.to_bytes(4, 'little')

    @staticmethod
    def reverse(byte_array: bytes) -> bytes:
        return bytes(reversed(byte_array))

    @staticmethod
    def short_to_little_byte_array(number: int) -> bytes:
        return number.to_bytes(2, 'little')

    # @staticmethod
    # def sub_byte(byte_val: int, start: int, end: int) -> int:
    #     if start < end and start >= 0 and end <= 8:
    #         return (byte_val >> start) & (0xFF >> (8 - (end - start)))
    #     return 0
    @staticmethod
    def sub_byte(b, i, i2):
        if i >= i2 or i < 0 or i2 > 8:
            return 0
        unsigned_b = b & 0xFF  # 转换为无符号整数
        length = i2 - i
        mask = (0xFF >> (8 - length))
        return (unsigned_b >> i) & mask

    @staticmethod
    def to_bytes(number: Union[int, float], byteorder: str = DEFAULT_BYTEORDER) -> bytes:
        if isinstance(number, int):
            if -32768 <= number <= 32767:  # short range
                return number.to_bytes(2, byteorder, signed=number < 0)
            elif -2147483648 <= number <= 2147483647:  # int range
                return number.to_bytes(4, byteorder, signed=number < 0)
            else:  # long range
                return number.to_bytes(8, byteorder, signed=number < 0)
        elif isinstance(number, float):
            return struct.pack('d' if byteorder == 'little' else '>d', number)
        raise TypeError("Unsupported type for conversion")

    @staticmethod
    def to_hex_string(string: str) -> str:
        return " ".join(f"{ord(c):x}" for c in string)

    @staticmethod
    def to_int(byte_array: bytes, byteorder: str = DEFAULT_BYTEORDER) -> int:
        return int.from_bytes(byte_array, byteorder)

    @staticmethod
    def to_long(byte_array: bytes, byteorder: str = DEFAULT_BYTEORDER) -> int:
        return int.from_bytes(byte_array, byteorder)

    @staticmethod
    def to_short(byte_array: bytes, byteorder: str = DEFAULT_BYTEORDER) -> int:
        return int.from_bytes(byte_array, byteorder)

    @staticmethod
    def to_unsigned_int(byte_array: bytes, byteorder: str = DEFAULT_BYTEORDER) -> int:
        return ConvertUtils.to_int(byte_array, byteorder) & 0xFFFFFFFF

    @staticmethod
    def to_unsigned_short(byte_array: bytes, byteorder: str = DEFAULT_BYTEORDER) -> int:
        return ConvertUtils.to_short(byte_array, byteorder) & 0xFFFF
