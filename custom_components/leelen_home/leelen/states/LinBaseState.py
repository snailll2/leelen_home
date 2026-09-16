from dataclasses import dataclass


@dataclass
class LinBaseState:
    """设备状态基类 —— 数据对象 + 与旧代码兼容的访问器。

    字段即状态;get_/set_ 访问器供各平台实体与 CommonModel 兼容旧调用
    (重建时仅移除 Android 残留的 from_parcel/to_parcel/describe_contents)。
    """

    service_address: int = 0
    service_type: int = 0
    power_state: int = 0

    def get_power_state(self) -> int:
        return self.power_state

    def get_service_address(self) -> int:
        return self.service_address

    def get_service_type(self) -> int:
        return self.service_type

    def set_power_state(self, power_state: int):
        self.power_state = power_state

    def set_service_address(self, service_address: int):
        self.service_address = service_address

    def set_service_type(self, service_type: int):
        self.service_type = service_type

    def __str__(self):
        return str(self.__dict__)