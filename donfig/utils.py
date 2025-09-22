#!/usr/bin/env python
# Copyright (c) 2018 Donfig Developers
# Copyright (c) 2014-2018, Anaconda, Inc. and contributors
import os
import shutil
import tempfile
from contextlib import contextmanager, suppress


@contextmanager
def tmpfile(extension="", dir=None):
    extension = "." + extension.lstrip(".")
    handle, filename = tempfile.mkstemp(extension, dir=dir)
    os.close(handle)
    os.remove(filename)

    try:
        yield filename
    finally:
        if os.path.exists(filename):
            if os.path.isdir(filename):
                shutil.rmtree(filename)
            else:
                with suppress(OSError):
                    os.remove(filename)
