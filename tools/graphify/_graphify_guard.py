"""Runtime guard for graphify-safe: blocks network access and foreign subprocesses.

Installed into the dedicated graphify venv and loaded on every interpreter start
via ``zz_graphify_guard.pth``, so it also covers ProcessPoolExecutor workers.

It uses a PEP 578 audit hook, which cannot be removed once installed. This is
defense in depth on top of ``--code-only``: if a future graphify code path tries
to reach an LLM provider (HTTP SDK, urllib, or the ``claude`` CLI), the call
fails loudly instead of silently sending repository content off the machine.
"""

import os
import sys

_ALLOWED_EXECUTABLES = {"git"}
_NETWORK_EVENTS = {
    "socket.connect",
    "socket.connect_ex",
    "socket.sendto",
    "socket.sendmsg",
    "socket.getaddrinfo",
    "socket.gethostbyname",
    "socket.gethostbyname_ex",
    "socket.gethostbyaddr",
    "socket.getnameinfo",
    "urllib.Request",
    "http.client.connect",
}
_EXEC_EVENTS = {"os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.startfile"}

try:
    _PYTHON = os.path.realpath(sys.executable)
except Exception:  # pragma: no cover - extremely defensive
    _PYTHON = ""


def _blocked(what):
    raise PermissionError(f"graphify-safe guard: blocked {what}")


def _exe_name(executable, argv):
    target = executable
    if not target:
        if isinstance(argv, (str, bytes)):
            target = argv.split()[0] if argv.split() else ""
        elif argv:
            target = argv[0]
    target = os.fsdecode(target) if target else ""
    return target


def _hook(event, args):
    if event in _NETWORK_EVENTS:
        # Local AF_UNIX sockets (address is a path) are not network traffic.
        if event.startswith("socket.connect") and len(args) > 1 and isinstance(args[1], (str, bytes)):
            return
        _blocked(f"network access ({event})")
    elif event == "subprocess.Popen":
        target = _exe_name(args[0], args[1])
        if os.path.basename(target) in _ALLOWED_EXECUTABLES:
            return
        try:
            if _PYTHON and os.path.realpath(target) == _PYTHON:
                return
        except Exception:
            pass
        _blocked(f"subprocess {target!r}")
    elif event in _EXEC_EVENTS:
        _blocked(f"process execution ({event})")


# Unconditional on purpose: there is no environment switch to turn this off.
sys.addaudithook(_hook)
os.environ["GRAPHIFY_SAFE_GUARD_ACTIVE"] = "1"
