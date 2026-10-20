#!/usr/bin/env python3
"""Small filesystem helpers.

Every report / JSON file is written atomically (temp file in the same folder →
fsync → os.replace) so a crash, a power cut or an overlapping scheduled run can
never leave a half-written dashboard behind.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: Path | str, data: bytes) -> None:
  path = Path(path)
  path.parent.mkdir(parents=True, exist_ok=True)
  fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
  try:
    with os.fdopen(fd, "wb") as fh:
      fh.write(data)
      fh.flush()
      os.fsync(fh.fileno())
    os.replace(tmp, path)
    try:
      os.chmod(path, 0o644)
    except OSError:
      pass
  except BaseException:
    try:
      os.unlink(tmp)
    except OSError:
      pass
    raise


def atomic_write_text(path: Path | str, text: str, encoding: str = "utf-8") -> None:
  atomic_write_bytes(path, text.encode(encoding))
