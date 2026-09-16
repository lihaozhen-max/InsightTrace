from enum import StrEnum


class UserRole(StrEnum):
    ANALYST = "analyst"
    ADMIN = "admin"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class MessageType(StrEnum):
    TEXT = "text"
    STATUS = "status"
    TOOL = "tool"
    ERROR = "error"


class ToolStatus(StrEnum):
    STARTED = "started"
    SUCCESS = "success"
    FAILED = "failed"


class AttachmentParseStatus(StrEnum):
    PENDING = "pending"
    PARSING = "parsing"
    SUCCESS = "success"
    FAILED = "failed"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisMode(StrEnum):
    DEMO = "demo"
    MODEL = "model"


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
