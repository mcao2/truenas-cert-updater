#!/usr/bin/env python3

import warnings
warnings.warn(
    'This script is deprecated in favour of the "renew_update_cert.py" script. '
    'Please use that instead.',
    DeprecationWarning,
    stacklevel=2,
)
import pathlib
import sys
sys.path.append(str(pathlib.Path(__file__).parent))
from renew_update_cert import main as renew_update_cert_main

renew_update_cert_main()
