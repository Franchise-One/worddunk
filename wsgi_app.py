"""
PythonAnywhere (and other WSGI hosts) entry point.
Point your host's WSGI config at this file; `application` is the callable.
"""
import os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from server import wsgi_app as application  # noqa: E402
