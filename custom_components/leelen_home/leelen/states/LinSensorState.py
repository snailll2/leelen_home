from dataclasses import dataclass

from .LinBaseState import LinBaseState

@dataclass
class LinSensorState(LinBaseState):
    value = 0
    power: int = 0


    def get_value(self) :
        return self.value

    def set_value(self, value):
        self.value = value

    def set_power(self, power: int):
        self.power = power

    def get_power(self) -> int:
        return self.power