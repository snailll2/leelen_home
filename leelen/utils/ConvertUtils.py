import struct
from typing import List, Optional, Union

from .LogUtils import LogUtils


class ConvertUtils:
    DEFAULT_BYTEORDER = 'little'

    @staticmethod
    def byte_array_to_gbk_string(byte_array: bytes) -> str:
        try:
            return byte_array.decode('gbk')
        except UnicodeDecodeError:
            return ""

    @staticmethod
    def byte_array_to_iso_string(byte_array: bytes) -> str:
        try:
            return byte_array.decode('iso-8859-1')
        except UnicodeDecodeError:
            return ""

    @staticmethod
    def byte_array_to_mac(byte_array: bytes) -> str:
        if len(byte_array) < 6:
            return ""

        mac_parts = []
        for i in range(6):
            part = f"{byte_array[i]:02x}"
            mac_parts.append(part)

        return ":".join(mac_parts).upper()

    @staticmethod
    def byte_array_to_utf8_string(byte_array: bytes) -> str:
        try:
            return byte_array.decode('utf-8')
        except UnicodeDecodeError:
            return ""

    @staticmethod
    def byte_to_bcd(byte_array: bytes) -> str:
        result = []
        for byte in byte_array:
            result.append(str((byte & 0xF0) >> 4))
            result.append(str(byte & 0x0F))

        bcd_str = "".join(result)
        return bcd_str[1:] if bcd_str.startswith("0") else bcd_str

    @staticmethod
    def bytes_to_hex(byte_array: Optional[bytes], separator: str = '') -> str:
        if byte_array is None:
            return ""
        return separator.join(f"{byte:02x}" for byte in byte_array)

    @staticmethod
    def bytes_to_hex_string(byte_array: Optional[bytes]) -> str:
        if byte_array is None or len(byte_array) == 0:
            return None
        return "".join(f"{byte:02x}" for byte in byte_array)

    @staticmethod
    def bytes_to_ip(byte_array: bytes) -> str:
        return f"{byte_array[0]}.{byte_array[1]}.{byte_array[2]}.{byte_array[3]}"

    @staticmethod
    def bytes_to_ip_revert(byte_array: bytes) -> str:
        return f"{byte_array[3]}.{byte_array[2]}.{byte_array[1]}.{byte_array[0]}"

    @staticmethod
    def bytes_to_mac(byte_array: bytes) -> str:
        return ":".join(f"{byte:02x}" for byte in byte_array)

    @staticmethod
    def db_string2pro(string: str, length: int) -> bytes:
        byte_array = bytearray(string.encode())
        if len(byte_array) < length:
            byte_array.extend([0xFF] * (length - len(byte_array)))
        return bytes(byte_array[:length])

    @staticmethod
    def get_32_bit_bin_string(number: int) -> str:
        return f"{number:032b}"

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
    def get_int_string_bytes(string: str) -> bytes:
        return bytes([ord(c) for c in string])

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

    @staticmethod
    def get_simple_bin_string(number: int) -> str:
        binary = bin(number)[2:]  # Remove '0b' prefix
        return binary.lstrip('0') or '0'

    @staticmethod
    def get_unsigned_int(number: int) -> int:
        return number & 0xFFFFFFFF

    @staticmethod
    def get_unsigned_short(number: int) -> int:
        return number & 0xFFFF

    @staticmethod
    def hex2byte(hex_string: str) -> bytes:
        parts = hex_string.split()
        return bytes(int(part, 16) for part in parts)

    @staticmethod
    def hex_string_to_string(hex_string: str) -> str:
        if not hex_string:
            return None

        hex_string = hex_string.replace(" ", "")
        try:
            byte_array = bytes.fromhex(hex_string)
            return byte_array.decode('utf-8')
        except Exception:
            return hex_string

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
                # LogUtils.d(hex_str[pos:pos + 2])
                byte_list.append(int(hex_str[pos:pos + 2], 16))
        return bytes(byte_list)

    @staticmethod
    def hex_to_int(chars: List[str]) -> int:
        result = 0
        for char in chars:
            if 'A' <= char <= 'F':
                value = ord(char) - ord('A') + 10
            elif 'a' <= char <= 'f':
                value = ord(char) - ord('a') + 10
            else:
                value = int(char)
            result = result * 16 + value
        return result

    @staticmethod
    def int_to_little_byte_array(number: int) -> bytes:
        return number.to_bytes(4, 'little')

    @staticmethod
    def ip_to_bytes(ip_string: str) -> bytes:
        try:
            parts = list(map(int, ip_string.split('.')))
            return bytes([parts[3], parts[2], parts[1], parts[0]])
        except Exception:
            raise ValueError(f"{ip_string} is invalid IP")

    @staticmethod
    def print_byte_arr(tag: str, description: str, byte_array: bytes):
        hex_str = ConvertUtils.bytes_to_hex(byte_array, ' ')
        LogUtils.d(f"{tag}: {description}({len(byte_array)}) {hex_str}")

    @staticmethod
    def reverse(byte_array: bytes) -> bytes:
        return bytes(reversed(byte_array))

    @staticmethod
    def short_to_little_byte_array(number: int) -> bytes:
        return number.to_bytes(2, 'little')

    @staticmethod
    def str2bcd(string: str) -> bytes:
        if len(string) % 2 != 0:
            string = '0' + string

        result = bytearray()
        for i in range(0, len(string), 2):
            high = int(string[i])
            low = int(string[i + 1])
            result.append((high << 4) | low)

        return bytes(result)

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
    def sub_bytes(byte_array: bytes, start: int, length: int) -> bytes:
        return byte_array[start:start + length]

    @staticmethod
    def to_bytes(number: Union[int, float], byteorder: str = DEFAULT_BYTEORDER) -> bytes:
        if isinstance(number, int):
            if -32768 <= number <= 32767:  # short range
                return number.to_bytes(2, byteorder)
            elif -2147483648 <= number <= 2147483647:  # int range
                return number.to_bytes(4, byteorder)
            else:  # long range
                return number.to_bytes(8, byteorder)
        elif isinstance(number, float):
            return struct.pack('d' if byteorder == 'little' else '>d', number)
        raise TypeError("Unsupported type for conversion")

    @staticmethod
    def to_bytes_big(number: int) -> bytes:
        return ConvertUtils.to_bytes(number, 'big')

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
    def to_lower(string: str) -> str:
        return string.lower()

    @staticmethod
    def to_short(byte_array: bytes, byteorder: str = DEFAULT_BYTEORDER) -> int:
        return int.from_bytes(byte_array, byteorder)

    @staticmethod
    def to_unsigned_int(byte_array: bytes, byteorder: str = DEFAULT_BYTEORDER) -> int:
        return ConvertUtils.to_int(byte_array, byteorder) & 0xFFFFFFFF

    @staticmethod
    def to_unsigned_short(byte_array: bytes, byteorder: str = DEFAULT_BYTEORDER) -> int:
        return ConvertUtils.to_short(byte_array, byteorder) & 0xFFFF
