class BaseAck:
    """Base class for acknowledgment messages"""

    def __init__(self):

        self.ack: int = 0  # Using type hint for clarity

    def __str__(self) -> str:

        return f"BaseAck(ack={self.ack})"
