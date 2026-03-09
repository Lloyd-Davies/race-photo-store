import enum


class CommunicationStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    FAILED = "FAILED"
    DELIVERED = "DELIVERED"
    BOUNCED = "BOUNCED"
    BLOCKED = "BLOCKED"
    DEFERRED = "DEFERRED"


class CommunicationKind(str, enum.Enum):
    ORDER_CONFIRMED = "ORDER_CONFIRMED"
    DOWNLOAD_READY = "DOWNLOAD_READY"
    DELIVERY_RESET = "DELIVERY_RESET"
