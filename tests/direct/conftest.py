"""Conftest for GenCheck direct tests.

Works around a Windows-specific bug in gltest 0.29.2's direct-mode loader:
`_inject_message_to_fd0` unlinks its temp file while the dup2'd fd 0 still
holds it open. POSIX allows deleting open files; Windows raises
PermissionError. The injection itself succeeds — only the cleanup fails — so
we swallow just that error and let the OS temp-dir cleanup collect the file.

Upstream: https://github.com/genlayerlabs/genvm (gltest/direct/loader.py)
"""

import os

import gltest.direct.loader as _gltest_loader

_orig_inject = _gltest_loader._inject_message_to_fd0


def _win_safe_inject_message_to_fd0(vm):
    real_unlink = os.unlink

    def soft_unlink(path, *args, **kwargs):
        try:
            return real_unlink(path, *args, **kwargs)
        except PermissionError:
            # Windows: fd 0 still references the temp file after dup2.
            return None

    os.unlink = soft_unlink
    try:
        return _orig_inject(vm)
    finally:
        os.unlink = real_unlink


_gltest_loader._inject_message_to_fd0 = _win_safe_inject_message_to_fd0
