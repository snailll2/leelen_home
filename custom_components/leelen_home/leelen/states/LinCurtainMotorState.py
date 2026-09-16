from dataclasses import dataclass

from .LinBaseState import LinBaseState


@dataclass
class LinCurtainMotorState(LinBaseState):
    progress: int = 0
    angle: int = 0
    is_changing: bool = False

    def get_progress(self) -> int:
        return self.progress

    def set_progress(self, value: int):
        self.progress = value

    def get_angle(self) -> int:
        return self.angle

    def set_angle(self, value: int):
        self.angle = value

    def is_changing_state(self) -> bool:
        return self.is_changing

    def set_changing(self, value: bool):
        self.is_changing = value