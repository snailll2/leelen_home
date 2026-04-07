from dataclasses import dataclass


@dataclass
class LinBaseState:
    service_address: int = 0
    service_type: int = 0
    power_state: int = 0

    def __post_init__(self):
        # You can add any additional initialization logic here
        pass

    @classmethod
    def from_parcel(cls, parcel_data: bytes):
        """
        Deserialize the state from a byte array (simulating Parcel).
        """
        service_address, service_type, power_state = parcel_data
        return cls(service_address, service_type, power_state)

    def to_parcel(self):
        """
        Serialize the state into a byte array (simulating Parcel).
        """
        return bytes([self.service_address, self.service_type, self.power_state])

    def describe_contents(self):
        """
        Simulating Android's describeContents method.
        Returns a flag indicating special objects in the parcel.
        """
        return 0

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
