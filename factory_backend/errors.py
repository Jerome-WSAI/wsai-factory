"""Shared errors and env helpers for factory_backend."""

from __future__ import annotations

import os


class FactoryError(Exception):
    def __init__(self, code: str, message: str, http_status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not isinstance(value, str) or value.strip() == "":
        raise FactoryError(
            "missing_env",
            f"required env {name} is missing or empty",
            500,
        )
    return value.strip()
