import enum

class LobbyStatus(enum.Enum):
    """Status of the lobby"""
    READY = "READY"
    WAITING_TO_START = "WAITING_TO_START"
    IN_GAME = "IN_GAME"