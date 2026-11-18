#!/usr/bin/env python3
"""Liftoff — kaynak ağacından doğrudan çalıştırmak için başlatıcı.

Kurulu sürüm ``python3 -m liftoff`` kullanır; bu dosya yalnızca
depoyu indirip denemek isteyenler için kolaylık sağlar.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(os.path.realpath(__file__))))

from liftoff.ui import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
