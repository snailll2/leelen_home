"""窗帘电机「更改方向 / 重置行程」按钮测试。

背景:官方 App 改电机方向/重置行程走 App 设备透传指令(apk 逆向
``BaseManagerImpl.appDevicePassThrough``),cmd = PASS_THROUGH_APP_DEVICE([1, 6]),
body = ``[01 TA][len][0x64 写私有属性][01 A3 电机属性][val_len][val]``,
目标地址=**逻辑通道地址**(dump.db 实测:dev 224/240 的可写属性 163 挂 logic_addr
225/241)。值字节:bit0=方向(0正/1反),bit1=重置行程(置1触发)。

覆盖:
- ``write_private_property`` 写帧字节(真实协议类拼帧,钉死 body 与头部 cmd)
- ``_build_entities``:窗帘电机设备 → [定位, 方向, 重置] 三个按钮;无窗帘通道
  设备仍返回单个定位按钮(历史行为不回归)
- ``CurtainMotorDirectionButton.async_press``:翻转方向并下发 value=1-方向
- ``CurtainMotorResetButton.async_press``:保留方向位并下发 value=方向+2
- ``_curtain_motor_channels`` 门控:非窗帘/无属性/只读属性不建
- ``config_flow._collect_expected_unique_ids``:两个新 unique_id 进清理白名单

运行(在 wsl HA 容器):
    docker exec ha-test python3 -m pytest tests/test_curtain_motor.py -q
"""
import asyncio
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, "/config")

from custom_components.leelen_home.button import (  # noqa: E402
    CURTAIN_MOTOR_DIRECTION_PREFIX, CURTAIN_MOTOR_RESET_PREFIX,
    CurtainMotorDirectionButton, CurtainMotorResetButton, _build_entities,
    _curtain_motor_channels,
)
from custom_components.leelen_home.config_flow import _collect_expected_unique_ids  # noqa: E402
from custom_components.leelen_home.leelen.common import LanProtocolCmd  # noqa: E402
from custom_components.leelen_home.leelen.common.LeelenType import (  # noqa: E402
    APCIType, DeviceType, LogicDeviceType, PropertyId,
)
from custom_components.leelen_home.leelen.models.ControlModel import ControlModel  # noqa: E402
from custom_components.leelen_home.leelen.common.CommonModel import CommonModel  # noqa: E402

#: 真实 dump.db:窗帘电机设备 224/240,逻辑通道 570(纱帘/布帘),可写 163 在 225/241。
_MOTOR_DEV = 224
_MOTOR_LOGIC = 225
_MOTOR_TYPE = 570


def _curtain_device(dev_addr=_MOTOR_DEV, logic=225, name="纱帘", dev_name="窗帘电机",
                    val=b"\x00", read_only=0, cur_flag=True):
    """窗帘电机假设备:dev 224 + logic 225(570)+ 可写属性 163 @ logic addr。

    属性 id 是整数 163(property_tbl 行),与 LIGHT_PATTERN 的 136 一样按整数存。
    """
    logic_srv = [{"logic_type": _MOTOR_TYPE, "logic_addr": logic,
                  "dev_addr": dev_addr, "logic_name": name}]
    all_property = []
    if cur_flag:
        all_property = [{"property_id": 163,
                         "read_only": read_only, "val_length": 1, "val": val,
                         "addr": logic}]
    return {"dev_name": dev_name, "dev_addr": dev_addr,
            "logic_srv": logic_srv, "all_property": all_property}


def _mock_config_entry():
    return Mock(entry_id="test", data={})


# ------------------------------------------------- 写帧字节(真实编码)

class TestPassThroughWriteBytes(unittest.TestCase):
    """用真实 AppDevicePassThroughLanProtocol 复现电机方向/重置写帧,钉死字节。

    body = [01 TA][len][64][01 A3][val_len][val] → 01 05 64 01 A3 01 xx;
    完整帧 head:cmd 位于 34:36 = [1, 6](PASS_THROUGH_APP_DEVICE)。
    """

    @staticmethod
    def _frame(value: bytes):
        from custom_components.leelen_home.leelen.protocols.AppDevicePassThroughLanProtocol import (
            AppDevicePassThroughLanProtocol)

        from custom_components.leelen_home.leelen.entity.GatewayInfo import GatewayInfo
        from custom_components.leelen_home.leelen.utils.ConvertUtils import ConvertUtils
        from custom_components.leelen_home.leelen.entity.User import User

        proto = AppDevicePassThroughLanProtocol()
        payload = bytearray()
        payload.extend(bytes([1]))  # PassThroughType.TA == bytes([1])
        payload.append(4 + len(value))
        payload.extend(APCIType.WRITE_PRIVATE_PROPERTY)
        payload.extend(PropertyId.CURTAIN_MOTOR)
        payload.append(len(value))
        payload.extend(value)
        proto.set_payload_data(bytes(payload))
        service_addr = ConvertUtils.short_to_little_byte_array(_MOTOR_LOGIC)
        return proto.get_request_data(
            ConvertUtils.get_long_address_by_type(DeviceType.APP, 1),  # 仅需占位地址
            GatewayInfo.get_instance().gateway_desc,
            service_addr)

    def test_cmd_is_pass_through_app_device(self):
        from custom_components.leelen_home.leelen.protocols.AppDevicePassThroughLanProtocol import (
            AppDevicePassThroughLanProtocol)
        proto = AppDevicePassThroughLanProtocol()
        assert proto.cmd == LanProtocolCmd.PASS_THROUGH_APP_DEVICE == bytes([1, 6])
        assert proto.payload_type == bytes([0])

    def test_direction_forward_body_bytes(self):
        # 方向 0(正转)→ value = 1 - 0 = 1 → 01 05 64 01 A3 01 01
        frame = self._frame(bytes([1]))
        assert frame[41:48] == bytes.fromhex("01056401a30101"), frame.hex()

    def test_direction_reverse_body_bytes(self):
        # 方向 1(反转)→ 改方向 → value = 1 - 1 = 0 → 01 05 64 01 A3 01 00
        frame = self._frame(bytes([0]))
        assert frame[41:48] == bytes.fromhex("01056401a30100"), frame.hex()

    def test_reset_direction_forward_body_bytes(self):
        # 方向 0 + 重置 → value = 0 + 2 = 2 → 01 05 64 01 A3 01 02
        frame = self._frame(bytes([2]))
        assert frame[41:48] == bytes.fromhex("01056401a30102"), frame.hex()

    def test_reset_direction_reverse_body_bytes(self):
        # 方向 1 + 重置 → value = 1 + 2 = 3 → 01 05 64 01 A3 01 03
        frame = self._frame(bytes([3]))
        assert frame[41:48] == bytes.fromhex("01056401a30103"), frame.hex()

    def test_full_frame_head_carries_cmd_0106(self):
        frame = self._frame(bytes([1]))
        assert frame[34:36] == bytes([1, 6]), frame[:41].hex()
        # 帧尾带 CRC8 校验字节
        assert len(frame) == 41 + 7 + 1


# ------------------------------------------------- _curtain_motor_channels 门控

class TestCurtainMotorChannels(unittest.TestCase):
    def test_curtain_with_writable_prop_returns_channel(self):
        got = _curtain_motor_channels(_curtain_device(val=b"\x00"))
        assert len(got) == 1
        logic_srv, prop_row = got[0]
        assert logic_srv["logic_addr"] == _MOTOR_LOGIC
        assert prop_row["val"] == b"\x00"

    def test_readonly_prop_no_channel(self):
        assert _curtain_motor_channels(_curtain_device(read_only=1)) == []

    def test_no_prop_no_channel(self):
        assert _curtain_motor_channels(_curtain_device(cur_flag=False)) == []

    def test_non_curtain_logic_type_no_channel(self):
        dev = _curtain_device()
        dev["logic_srv"] = [{"logic_type": 518, "logic_addr": 225,
                             "dev_addr": _MOTOR_DEV, "logic_name": "插座"}]
        assert _curtain_motor_channels(dev) == []


# ------------------------------------------------- 实体构建

class TestBuildCurtainMotorButtons(unittest.TestCase):
    def test_curtain_builds_locate_plus_direction_plus_reset(self):
        entities = _build_entities(_curtain_device(val=b"\x00"), _mock_config_entry())
        assert isinstance(entities, list), entities
        assert len(entities) == 3, entities
        # 定位 + 方向 + 重置(顺序按 _build_entities 的 append 次序)
        locate, direction, reset = entities
        assert isinstance(locate, type(entities[0]))
        assert direction.unique_id == f"{CURTAIN_MOTOR_DIRECTION_PREFIX}_{_MOTOR_LOGIC}"
        assert direction.name == "纱帘 更改方向"
        assert direction.icon == "mdi:swap-vertical"
        assert direction.entity_category.value == "config"
        assert reset.unique_id == f"{CURTAIN_MOTOR_RESET_PREFIX}_{_MOTOR_LOGIC}"
        assert reset.name == "纱帘 重置行程"
        assert reset.icon == "mdi:restore"
        assert reset.entity_category.value == "config"
        # 初始方向:属性 163 现值 bit0 = 0(正转)
        assert direction._state["direction"] == 0

    def test_curtain_reverse_initial_direction(self):
        entities = _build_entities(_curtain_device(val=b"\x01"), _mock_config_entry())
        direction = [e for e in entities if isinstance(e, CurtainMotorDirectionButton)][0]
        assert direction._state["direction"] == 1

    def test_non_curtain_device_single_locate_unchanged(self):
        # 无窗帘通道的定位设备仍返回单个按钮(历史行为,test_panel_locate 依赖)。
        from custom_components.leelen_home.button import DeviceLocateButton
        dev = _curtain_device(cur_flag=False, dev_addr=32)
        dev["logic_srv"] = [{"logic_type": LogicDeviceType.ZIGBEE_SMART_WALL_SOCKET,
                             "logic_addr": 33, "dev_addr": 32, "logic_name": "插座"}]
        entities = _build_entities(dev, _mock_config_entry())
        assert isinstance(entities, DeviceLocateButton)
        assert entities.unique_id == "leelen_device_locate_32"


# ------------------------------------------------- 按下转发

class TestCurtainMotorPress(unittest.TestCase):
    def test_direction_press_flips_and_writes(self):
        self._pressed = None

        def _fake_write(service_id, property_id, value):
            self._pressed = (service_id, property_id, value)

        with patch.object(ControlModel, "write_private_property",
                          side_effect=_fake_write):
            entities = _build_entities(_curtain_device(val=b"\x00"),
                                       _mock_config_entry())
            direction = [e for e in entities
                         if isinstance(e, CurtainMotorDirectionButton)][0]
            asyncio.run(direction.async_press())

        svc, pid, val = self._pressed
        assert svc == _MOTOR_LOGIC                       # 逻辑通道地址
        assert pid == PropertyId.CURTAIN_MOTOR           # bytes([1, 163])
        assert val == bytes([1])                         # 1 - 0(正转→反转)
        assert direction._state["direction"] == 1        # 乐观更新,重置按钮共享

    def test_direction_then_reset_preserves_new_direction(self):
        # 先翻转方向(0→1),再重置 → value 必须带新方向位:1 + 2 = 3。
        calls = []

        def _fake_write(service_id, property_id, value):
            calls.append((service_id, property_id, value))

        with patch.object(ControlModel, "write_private_property",
                          side_effect=_fake_write):
            entities = _build_entities(_curtain_device(val=b"\x00"),
                                       _mock_config_entry())
            direction = [e for e in entities
                         if isinstance(e, CurtainMotorDirectionButton)][0]
            reset = [e for e in entities
                     if isinstance(e, CurtainMotorResetButton)][0]
            asyncio.run(direction.async_press())
            asyncio.run(reset.async_press())

        assert len(calls) == 2
        # 方向按下:1 - 0 = 1
        assert calls[0][2] == bytes([1])
        # 重置按下:新方向 1 + 2 = 3(direction/state 共享 dict 保证一致性)
        assert calls[1][0] == _MOTOR_LOGIC
        assert calls[1][1] == PropertyId.CURTAIN_MOTOR
        assert calls[1][2] == bytes([3])

    def test_control_model_builds_payload_and_requests(self):
        """经 ControlModel.write_private_property 全链路:帧经 HeartbeatService 送出。"""
        from custom_components.leelen_home.leelen.HeartbeatService import HeartbeatService
        from custom_components.leelen_home.leelen.entity.User import User

        ControlModel.reset_instance()  # 单例重建,避免此前用例 patch 残留
        # 登录态:account_id 为服务端正整数(默认 -1 会让 to_bytes 溢出,与 device_hint 同理)。
        User.get_instance().account_id = 1
        captured = {}

        def _fake_request(data):
            captured["data"] = data

        with patch.object(HeartbeatService, "request", side_effect=_fake_request):
            ControlModel.get_instance().write_private_property(
                _MOTOR_LOGIC, PropertyId.CURTAIN_MOTOR, bytes([1]))

        assert captured["data"] is not None
        frame = captured["data"]
        assert frame[34:36] == bytes([1, 6])
        assert frame[41:48] == bytes.fromhex("01056401a30101"), frame.hex()

    def test_update_state_is_awaitable_noop(self):
        """按钮无状态但挂在电机 logic_addr 上,会被 StateUpdateSubscriber 派发到。

        基类 ``_handle_state_event`` 固定 ``await self.update_state(state)``:实现
        缺失曾是 AttributeError,同步实现则 ``await None`` 抛 TypeError(两种线上
        都炸过)。钉死:必须是协程且可空转。
        """
        for cls in (CurtainMotorDirectionButton, CurtainMotorResetButton):
            entity = cls(_MOTOR_LOGIC, _MOTOR_DEV, "纱帘", "窗帘电机",
                         _mock_config_entry(), {"direction": 0})
            result = entity.update_state(None)
            assert asyncio.iscoroutine(result), f"{cls.__name__}.update_state 需为协程"
            asyncio.run(result)  # 可 await 且不抛
            # 完整走一遍基类派发路径:匹配地址 + get_cur_state + await + 写状态。
            # 实体未挂 hass,async_write_ha_state 一并 mock 掉。
            event = Mock(logic_address=_MOTOR_LOGIC, function_id=1, state=b"")
            with patch.object(CommonModel, "get_instance"), \
                    patch.object(entity, "async_write_ha_state"):
                asyncio.run(entity._handle_state_event(event))


# ------------------------------------------------- config_flow 白名单

class TestCollectExpectedUniqueIdsMotor(unittest.TestCase):
    def test_curtain_device_adds_two_motor_ids(self):
        got = _collect_expected_unique_ids([_curtain_device()])
        assert f"{CURTAIN_MOTOR_DIRECTION_PREFIX}_{_MOTOR_LOGIC}" in got
        assert f"{CURTAIN_MOTOR_RESET_PREFIX}_{_MOTOR_LOGIC}" in got
        # 定位按设备(dev_addr 224)同样成立,三个按钮都该在白名单里。
        assert "leelen_device_locate_224" in got
        assert "leelen_logic_addr_225" in got

    def test_readonly_motor_no_ids(self):
        got = _collect_expected_unique_ids([_curtain_device(read_only=1)])
        assert not any(uid.startswith(CURTAIN_MOTOR_DIRECTION_PREFIX) for uid in got), got
        assert not any(uid.startswith(CURTAIN_MOTOR_RESET_PREFIX) for uid in got), got


if __name__ == "__main__":
    unittest.main()