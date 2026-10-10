"""Tiny stage runner: each stage is a function that takes data and returns data."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

Stage = Callable[[Any], Any]


class Pipeline:
    def __init__(self, stages: list[tuple[str, Stage]]):
        self.stages = stages

    def run(self, data: Any = None) -> Any:
        for name, stage in self.stages:
            start = time.perf_counter()
            log.info("stage '%s' started", name)
            try:
                data = stage(data)
            except Exception:
                log.exception("stage '%s' failed", name)
                raise
            log.info("stage '%s' done in %.2fs", name, time.perf_counter() - start)
        return data
