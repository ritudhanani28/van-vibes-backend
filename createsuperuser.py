#!/usr/bin/env python3
import os
import sys

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.cli import createsuperuser

if __name__ == "__main__":
    try:
        createsuperuser()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
