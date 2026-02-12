from __future__ import annotations

import json
from pathlib import Path
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from .logging import get_logger

T = TypeVar("T", bound=BaseModel)
logger = get_logger()


def load_json(path: Path, model: Type[T], default: T) -> T:
    if path.exists():
        try:
            raw = path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            logger.warning("load_json read failed path=%s error=%s", path, exc)
            return default
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("load_json invalid json path=%s error=%s", path, exc)
            return default
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            logger.warning("load_json validation failed path=%s error=%s", path, exc)
            return default
    return default


def save_json(path: Path, model: BaseModel) -> None:
    path.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
