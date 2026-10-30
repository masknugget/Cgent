"""Stable domain errors shared by execution services and HTTP handlers."""


class HarnessError(Exception):
    """An expected failure with a stable API code and HTTP status."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class WorkspaceNotFoundError(HarnessError):
    def __init__(self, workspace_id: str) -> None:
        super().__init__("workspace_not_found", "The workspace was not found", 404)
        self.workspace_id = workspace_id


class InvalidPathError(HarnessError):
    def __init__(self, message: str = "The requested path is invalid") -> None:
        super().__init__("invalid_path", message, 400)


class PathOutsideWorkspaceError(HarnessError):
    def __init__(self) -> None:
        super().__init__(
            "path_outside_workspace", "The requested path is outside the workspace", 403
        )


class FileNotFoundError(HarnessError):
    def __init__(self) -> None:
        super().__init__("file_not_found", "The requested file was not found", 404)


class FileConflictError(HarnessError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, 409)


class PayloadTooLargeError(HarnessError):
    def __init__(self, message: str = "The request is too large") -> None:
        super().__init__("payload_too_large", message, 413)


class InvalidTextError(HarnessError):
    def __init__(self) -> None:
        super().__init__("invalid_text", "Only UTF-8 text files are supported", 422)


class InvalidEditError(HarnessError):
    def __init__(self, message: str) -> None:
        super().__init__("invalid_edit", message, 422)


class CommandRejectedError(HarnessError):
    def __init__(self, message: str = "The command is not allowed") -> None:
        super().__init__("command_rejected", message, 403)


class ShellCapacityExceededError(HarnessError):
    def __init__(self) -> None:
        super().__init__(
            "shell_capacity_exceeded", "The service has no available Shell capacity", 409
        )


class AgentTimeoutError(HarnessError):
    def __init__(self) -> None:
        super().__init__("agent_timeout", "The Agent invocation exceeded its deadline", 504)


class ModelUnavailableError(HarnessError):
    def __init__(self, message: str = "The model provider is unavailable") -> None:
        super().__init__("model_unavailable", message, 502)


class AgentStepLimitError(HarnessError):
    def __init__(self) -> None:
        super().__init__("agent_step_limit", "The Agent reached its model loop limit", 409)


class ServiceStoppingError(HarnessError):
    def __init__(self) -> None:
        super().__init__("service_stopping", "The service is shutting down", 503)
