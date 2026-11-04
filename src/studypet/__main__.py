"""`pythonw.exe -m studypet` 또는 `python.exe -m studypet --console` 진입점."""
from __future__ import annotations

import os
import sys

from studypet.app import run_app


def main() -> None:
    code = 1
    try:
        code = int(run_app() or 0)
    finally:
        os._exit(code)


if __name__ == "__main__":
    main()

