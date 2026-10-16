"""Thay biến {{TEN}} trong định nghĩa test và che giá trị secret khi ghi log."""

import re
from typing import Any

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]{0,99})\s*\}\}")
MASK = "***"


class MissingVariableError(Exception):
    pass


class Variables:
    def __init__(self, values: dict[str, str], secrets: set[str]) -> None:
        self._values = dict(values)
        self._secret_keys = set(secrets)

    def as_dict(self) -> dict[str, str]:
        """Toàn bộ giá trị (gồm secret), chỉ dùng để chuyển vào sandbox script; không ghi log."""
        return dict(self._values)

    def copy(self) -> "Variables":
        return Variables(self._values, self._secret_keys)

    def set(self, key: str, value: Any) -> None:
        self._values[key] = "" if value is None else str(value)

    def get(self, key: str) -> str:
        if key not in self._values:
            raise MissingVariableError(f"Chưa khai báo biến {{{{{key}}}}}")
        return self._values[key]

    def render(self, value: Any) -> Any:
        """Thay biến trong chuỗi, dict, list (đệ quy). Chuỗi chỉ gồm một biến giữ nguyên kiểu chuỗi."""
        if isinstance(value, str):
            return PLACEHOLDER.sub(lambda m: self.get(m.group(1)), value)
        if isinstance(value, dict):
            return {self.render(k): self.render(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.render(v) for v in value]
        return value

    @property
    def secret_values(self) -> list[str]:
        vals = [self._values[k] for k in self._secret_keys if self._values.get(k)]
        # Che chuỗi dài trước để không để lộ phần còn lại khi secret này chứa secret khác.
        return sorted(vals, key=len, reverse=True)

    def mask(self, text: str) -> str:
        for v in self.secret_values:
            if len(v) >= 3:
                text = text.replace(v, MASK)
        return text

    def mask_obj(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.mask(value)
        if isinstance(value, dict):
            return {k: self.mask_obj(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.mask_obj(v) for v in value]
        return value
