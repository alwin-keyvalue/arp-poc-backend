from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EmailHeader:
    name: str | None = None
    value: str | None = None
