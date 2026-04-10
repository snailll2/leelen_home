from dataclasses import dataclass

from .LinBaseState import LinBaseState

@dataclass
class LinCurtainMotorState(LinBaseState):
    progress: int = 0
    angle: int = 0
    is_changing: bool = False

    @classmethod
    def from_parcel(cls, parcel_data: bytes):
        """
        Deserialize the state from a byte array (simulating Parcel).
        Byte layout:
        [service_address, service_type, power_state, progress, angle, is_changing (0 or 1)]
        """
        if len(parcel_data) < 6:
            raise ValueError("Parcel data too short")
        service_address = parcel_data[0]
        service_type = parcel_data[1]
        power_state = parcel_data[2]
        progress = parcel_data[3]
        angle = parcel_data[4]
        is_changing = bool(parcel_data[5])
        return cls(
            service_address=service_address,
            service_type=service_type,
            power_state=power_state,
            progress=progress,
            angle=angle,
            is_changing=is_changing
        )

    def to_parcel(self) -> bytes:
        """
        Serialize the state into a byte array (simulating Parcel).
        """
        return bytes([
            self.service_address,
            self.service_type,
            self.power_state,
            self.progress,
            self.angle,
            1 if self.is_changing else 0
        ])

    def describe_contents(self) -> int:
        # 可用于描述内容类型（例如 parcelable 接口中）
        return 0

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
