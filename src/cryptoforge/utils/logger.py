"""Structured logging setup."""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path


class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "time": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "msg": record.getMessage(),
        })


def setup_logging(level: str = "INFO", log_dir: str = "data/logs"):
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("cryptoforge")
    root.setLevel(getattr(logging, level))
    root.handlers.clear()

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)8s] %(name)s: %(message)s", datefmt="%H:%M:%S"))
    root.addHandler(ch)

    # File (JSON)
    fh = logging.FileHandler(f"{log_dir}/bot_{datetime.now():%Y-%m-%d}.log")
    fh.setFormatter(JSONFormatter())
    root.addHandler(fh)

    return root
