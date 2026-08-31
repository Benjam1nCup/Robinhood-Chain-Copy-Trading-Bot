"""File + stdout logging."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path


def setup_logging(level: str, log_file: str, timestamp_name: bool = True) -> logging.Logger:
    log = logging.getLogger("rh_copy")
    log.setLevel(getattr(logging, level.upper(), logging.INFO))
    log.handlers.clear()
    log.propagate = False

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(sh)

    if log_file:
        path = Path(log_file)
        if timestamp_name:
            ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            path = path.parent / f"{path.stem}_{ts}{path.suffix or '.log'}"
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
        log.info("[LOG] writing %s", path)
    return log
