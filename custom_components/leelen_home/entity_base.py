"""立林实体公共基类。

light/switch/sensor/cover/climate 五个平台的实体此前各自重复
unique_id / name / device_info 与同一套 __init__ 样板,统一收敛到这里。
``StateUpdateSubscriber`` 已内含状态订阅与卸载注销逻辑,平台实体无需再挂。
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo

from .state_subscription import StateUpdateSubscriber


class LeelenEntity(StateUpdateSubscriber):
    """所有立林逻辑通道实体的公共部分。

    - ``_logic_addr``:网关内逻辑地址,决定 unique_id 并用于匹配状态事件;
    - ``_device_id``:物理设备地址(dev_addr),决定 device registry 归属;
    - ``_name``/``_device_name``:逻辑通道名与设备名。
    """

    def __init__(
        self,
        logic_addr,
        device_id: str,
        name: str,
        dev_name: str,
        config_entry: ConfigEntry,
    ) -> None:
        self._logic_addr = logic_addr
        self._device_id = device_id
        self._name = name
        self._device_name = dev_name
        self._config_entry = config_entry
        self._prop_on = False  # 通用开关态;纯传感器子类不用

    @property
    def unique_id(self) -> str:
        return f"leelen_logic_addr_{self._logic_addr}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={("LEELEN_HOME", self._device_id)},
            name=self._device_name,
            manufacturer="LEELEN",
        )

    @property
    def is_on(self) -> bool | None:
        """Return if the entity is on."""
        return self._prop_on
