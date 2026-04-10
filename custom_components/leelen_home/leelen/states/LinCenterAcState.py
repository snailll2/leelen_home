from dataclasses import dataclass

from .LinBaseState import LinBaseState


@dataclass
class LinCenterAcState(LinBaseState):
    mode: int = 0
    speed: int = 0
    setting_temperature: int = 0
    room_temperature: float = 0.0
    is_break_down: bool = False

    def get_mode(self) -> int:
        return self.mode

    def get_speed(self) -> int:
        return self.speed

    def get_setting_temperature(self) -> int:
        return self.setting_temperature

    def get_room_temperature(self) -> float:
        return self.room_temperature

    def is_break_down(self) -> bool:
        return self.is_break_down

    def set_mode(self, mode: int):
        self.mode = mode

    def set_speed(self, speed: int):
        self.speed = speed

    def set_setting_temperature(self, setting_temperature: int):
        self.setting_temperature = setting_temperature

    def set_room_temperature(self, room_temperature: float):
        self.room_temperature = room_temperature

    def set_break_down(self, is_break_down: bool):
        self.is_break_down = is_break_down

    def from_parcel(self, parcel_data: bytes):
        """
        从字节数组恢复对象（模拟 Parcel 功能）。
        """
        service_address, service_type, power_state, mode, speed, setting_temperature, room_temperature, is_break_down = parcel_data
        return LinCenterAcState(
            service_address, service_type, power_state,
            mode, speed, setting_temperature, room_temperature, is_break_down
        )

    def to_parcel(self):
        """
        序列化对象为字节数组（模拟 Parcel）。
        """
        return bytes([
            self.service_address, self.service_type, self.power_state,
            self.mode, self.speed, self.setting_temperature,
            int(self.room_temperature), int(self.is_break_down)
        ])
