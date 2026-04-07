from .BaseAck import BaseAck


class LoginAck(BaseAck):
    """
    Represents a login acknowledgment response from the gateway.
    Inherits from BaseAck and adds a timestamp field.
    """

    def __init__(self):
        super().__init__()
        self.timestamp: int = 0  # Using int since Python doesn't have a dedicated long type

    def __str__(self) -> str:
        return f"LoginAck(timestamp={self.timestamp})"
