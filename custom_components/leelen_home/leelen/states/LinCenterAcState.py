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

    def get_break_down(self) -> bool:
        """原方法名 is_break_down 与 dataclass 字段同名,实例上永远取不到该方法
        (属性查找先命中实例字典),且方法体自身也会返回字段而非布尔结果。
        改名以与 get_mode/get_speed 等保持一致。"""
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