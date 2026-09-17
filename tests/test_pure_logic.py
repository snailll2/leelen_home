"""纯逻辑单元测试 —— 不依赖 HA 运行时,可在任何 Python(含 WSL HA 容器)执行。

覆盖:
- ConvertUtils 字节/十六进制/整型转换
- TlvUtils  TLV 编码/解码往返
- AesCoder  AES-ECB 加解密往返

运行(在 custom_components 上层的 wsl HA 容器):
    docker exec ha-test python3 -m unittest discover -s /config/tests -v
"""
import sys
import unittest

sys.path.insert(0, "/config/custom_components")

from leelen_home.leelen.utils.ConvertUtils import ConvertUtils
from leelen_home.leelen.utils.TlvUtils import TlvUtils, TlvInfo
from leelen_home.leelen.utils.AesCoder import AesCoder
from leelen_home.room_sync import compute_device_room_map


class TestConvertUtils(unittest.TestCase):
    def test_bytes_to_hex(self):
        self.assertEqual(ConvertUtils.bytes_to_hex(b"\x0f\xff"), "0fff")
        self.assertEqual(ConvertUtils.bytes_to_hex(None), "")

    def test_hex_and_bytes_roundtrip(self):
        for raw in (b"\x01\x02\xff\x00", b"\xab\xcd\xef", b"\x00"):
            self.assertEqual(ConvertUtils.hex_to_bytes(ConvertUtils.bytes_to_hex(raw)), raw)

    def test_reverse(self):
        self.assertEqual(ConvertUtils.reverse(b"\x01\x02\x03"), b"\x03\x02\x01")
        self.assertEqual(ConvertUtils.reverse(b""), b"")

    def test_int_bytes_roundtrip(self):
        # 非负数:to_bytes/to_int 往返一致
        for n in (1, 127, 128, 300, 70000, 123456):
            self.assertEqual(ConvertUtils.to_int(ConvertUtils.to_bytes(n)), n)

    def test_negative_two_complement(self):
        # 负数输出为双字节补码(小端);to_int 是无符号读取,故只断言字节输出
        self.assertEqual(ConvertUtils.to_bytes(-1), b"\xff\xff")
        self.assertEqual(ConvertUtils.to_bytes(-2), b"\xfe\xff")
        self.assertEqual(ConvertUtils.to_bytes(-32768), b"\x00\x80")

    def test_to_bytes_width(self):
        # 短整型→2 字节小端
        self.assertEqual(ConvertUtils.to_bytes(0x0102), b"\x02\x01")
        # 超短整范围→4 字节
        self.assertEqual(ConvertUtils.to_bytes(70000), (70000).to_bytes(4, "little"))

    def test_short_little(self):
        self.assertEqual(ConvertUtils.short_to_little_byte_array(0x1234), b"\x34\x12")

    def test_unsigned(self):
        self.assertEqual(ConvertUtils.get_unsigned_short(65537), 1)
        self.assertEqual(ConvertUtils.get_unsigned_int(0x1_0000_0001), 1)
        self.assertEqual(ConvertUtils.to_unsigned_short(b"\xff\xff"), 65535)

    def test_sub_bytes(self):
        self.assertEqual(ConvertUtils.sub_bytes(b"\x01\x02\x03\x04", 1, 2), b"\x02\x03")

    def test_mac_and_bin(self):
        self.assertEqual(ConvertUtils.bytes_to_mac(b"\xaa\xbb"), "aa:bb")
        self.assertEqual(ConvertUtils.get_32_bit_bin_string(5),
                         "00000000000000000000000000000101")

    def test_bytes_to_ip(self):
        self.assertEqual(ConvertUtils.bytes_to_ip(b"\xc0\xa8\x01\x64"), "192.168.1.100")


class TestTlvUtils(unittest.TestCase):
    def test_byte_split(self):
        self.assertEqual(TlvUtils.get_low_byte(0xA7), 7)
        self.assertEqual(TlvUtils.get_hig_byte(0xA7), 10)
        self.assertEqual(TlvUtils.get_comp_byte(10, 7), 0xA7)

    def test_encode_small_tlv(self):
        # type=1, len=2 → comp 0x12, 后接 2 字节值
        enc = TlvUtils.get_tlv_encode([TlvInfo(type=1, len=2, value=b"\x00\x01")])
        self.assertEqual(enc, b"\x12\x00\x01")

    def test_encode_decode_roundtrip(self):
        cases = [
            [TlvInfo(type=1, len=3, value=b"\x01\x02\x03")],
            [TlvInfo(type=200, len=2, value=b"\xab\xcd")],   # type 在 13..268 区间
            [
                TlvInfo(type=2, len=1, value=b"\x00"),
                TlvInfo(type=3, len=4, value=b"\xde\xad\xbe\xef"),
            ],
        ]
        for tlvs in cases:
            enc = TlvUtils.get_tlv_encode(tlvs)
            self.assertIsNotNone(enc)
            dec = TlvUtils.tlv_decode(enc, len(enc))
            self.assertEqual(len(dec), len(tlvs))
            for a, b in zip(tlvs, dec):
                self.assertEqual(a.type, b.type)
                self.assertEqual(a.len, b.len)
                self.assertEqual(a.value, b.value)


class TestRoomSync(unittest.TestCase):
    """room→area 同步的纯映射逻辑(compute_device_room_map)。

    需与 query_devices 产出的 device dict 结构兼容:
    {"dev_addr": int, "logic_srv": [{"room_id": int}, ...]}
    """

    @staticmethod
    def _dev(addr, rooms):
        """构造一个设备 dict;rooms 为各 logic 通道的 room_id 列表。"""
        return {
            "dev_addr": addr,
            "dev_name": f"dev{addr}",
            "logic_srv": [{"dev_addr": addr, "room_id": r} for r in rooms],
        }

    def test_empty_device_list(self):
        self.assertEqual(compute_device_room_map([]), {})

    def test_all_room_zero_maps_to_living_room(self):
        # room_id 0 就是「客厅」,与其他房间同等对待,不再跳过
        dev = {"dev_addr": 112, "logic_srv": [{"room_id": 0}, {"room_id": None}, {}]}
        self.assertEqual(compute_device_room_map([dev]), {112: 0})

    def test_nonzero_room_beats_default_zero(self):
        # 有刻意配置的非 0 房间时,默认值 0(客厅)不参与多数票
        self.assertEqual(compute_device_room_map([self._dev(224, [3, 0, 0])]), {224: 3})

    def test_single_room_maps(self):
        self.assertEqual(compute_device_room_map([self._dev(224, [3, 3, 0])]), {224: 3})

    def test_majority_wins_same_device(self):
        self.assertEqual(compute_device_room_map([self._dev(224, [3, 3, 5, 0])]), {224: 3})

    def test_tie_breaks_to_lower_room(self):
        self.assertEqual(compute_device_room_map([self._dev(224, [3, 5, 3, 5, 4])]), {224: 3})

    def test_string_room_id_coerced(self):
        self.assertEqual(compute_device_room_map([self._dev(224, ["3", "5", "3"])]), {224: 3})

    def test_multiple_devices_isolated(self):
        devices = [
            self._dev(224, [3, 3]),
            self._dev(144, [5, 0]),
            self._dev(16, [1]),
            self._dev(32, [0, 0]),  # 全 0 → 客厅(room 0)
        ]
        self.assertEqual(compute_device_room_map(devices), {224: 3, 144: 5, 16: 1, 32: 0})

    def test_string_numeric_dev_addr_coerced(self):
        dev = {"dev_addr": "224", "logic_srv": [{"room_id": 3}]}
        self.assertEqual(compute_device_room_map([dev]), {224: 3})

    def test_device_without_logic_srv(self):
        self.assertEqual(compute_device_room_map([{"dev_addr": 1}]), {})

    def test_zero_dev_addr_skipped(self):
        dev = {"dev_addr": 0, "logic_srv": [{"room_id": 3}]}
        self.assertEqual(compute_device_room_map([dev]), {})


class TestAesCoder(unittest.TestCase):
    def test_encrypt_decrypt_roundtrip(self):
        key = "test-key-1234567"
        plain = "hello leelen"
        enc = AesCoder.encrypt_with_key(plain, key)
        self.assertTrue(enc)
        self.assertEqual(AesCoder.decrypt(enc, key), plain)

    def test_ecb_block_roundtrip(self):
        key = b"\x01" * 16
        for data in (b"a" * 15, b"b" * 16, b"c" * 31):
            enc = AesCoder._encrypt(key, data)
            self.assertEqual(AesCoder._decrypt(key, enc), data)


if __name__ == "__main__":
    unittest.main()