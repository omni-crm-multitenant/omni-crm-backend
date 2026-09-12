from __future__ import annotations


class AppError(Exception):
    status_code = 400
    code = "APPLICATION_ERROR"
    title = "Application error"

    def __init__(self, detail: str | None = None):
        super().__init__(detail or self.code)
        self.detail = detail or self.code
