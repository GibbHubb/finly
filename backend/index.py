"""F34 — Vercel serverless entry point.

Deliberately inside `backend/`, which is the source root: `app` is a package
under it, so `from app.main import app` resolves here exactly as it does when
uvicorn runs locally.

Three things about this file are load-bearing, all learned on AP31 the day
before and none of them guessable from the docs:

1. **`app` must be assigned at the TOP LEVEL.** Vercel's Python builder finds
   the symbol by static analysis, before anything runs — a version that assigned
   it only inside a `try:` failed the BUILD with
   `Could not find a top-level "app", "application", or "handler"`.
2. **The entry's own directory is not on `sys.path`.** The function runs with
   cwd=/var/task and the module is imported by path, so the insert below is what
   makes `app.main` importable. `includeFiles` in vercel.json is the other half —
   it is relative to THIS directory, not the project root.
3. **The import is guarded.** A module-level exception on a serverless function
   surfaces as `FUNCTION_INVOCATION_FAILED` with no detail, and there is no
   runtime log retention on this plan to look it up in. The guard serves the
   traceback as a 500 instead. It hides nothing: every route still fails.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_IMPORT_ERROR = None


async def app(scope, receive, send):  # replaced below on a successful import
    """Minimal ASGI app that reports why the real one could not load."""
    if scope["type"] != "http":
        return
    body = ("finly failed to start.\n\n" + (_IMPORT_ERROR or "unknown")).encode()
    await send({
        "type": "http.response.start",
        "status": 500,
        "headers": [(b"content-type", b"text/plain; charset=utf-8")],
    })
    await send({"type": "http.response.body", "body": body})


try:
    from app.main import app  # type: ignore[assignment]  # noqa: F811 — the real one
except Exception:  # noqa: BLE001 — anything at all, we need to see it
    _IMPORT_ERROR = traceback.format_exc()

__all__ = ["app"]
