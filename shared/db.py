"""Shared database utilities: connection pool and audit logging."""
from __future__ import annotations

import asyncio
import functools
import json
import os
import ssl
from typing import Any, Callable, Optional

import asyncpg

# ── Connection pool ───────────────────────────────────────────────────────────

_pool: Optional[asyncpg.Pool] = None


def _build_ssl() -> Optional[ssl.SSLContext]:
    if os.getenv("PGSSL", "false").lower() in ("true", "1", "yes"):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


async def get_pool() -> asyncpg.Pool:
    """Return (or lazily create) the shared asyncpg connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=os.environ["PGHOST"],
            port=int(os.getenv("PGPORT", "5432")),
            user=os.environ["PGUSER"],
            password=os.environ["PGPASSWORD"],
            database=os.environ["PGDATABASE"],
            ssl=_build_ssl(),
            min_size=1,
            max_size=10,
            command_timeout=60,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ── Audit logging ─────────────────────────────────────────────────────────────

async def write_audit(
    agent: str,
    tool: str,
    params: Optional[dict],
    summary: Optional[str],
    status: str,
) -> None:
    """Fire-and-forget audit log write — never raises."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_audit_log (agent, tool, params, summary, status)
                VALUES ($1, $2, $3, $4, $5)
                """,
                agent,
                tool,
                json.dumps(params) if params else None,
                summary,
                status,
            )
    except Exception:
        pass  # never block the tool call on audit failure


def audit(agent_name: str) -> Callable:
    """
    Decorator factory.  Wraps an async tool function with audit logging.

    Usage::

        @audit("DIO")
        async def clip_to_bbox(table: str, west: float, ...) -> dict:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            params: dict = {}
            # capture keyword arguments for audit record
            try:
                import inspect
                sig = inspect.signature(fn)
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                params = {k: v for k, v in bound.arguments.items() if k != "self"}
            except Exception:
                pass

            status = "success"
            result = None
            try:
                result = await fn(*args, **kwargs)
                summary = str(result)[:500] if result is not None else None
            except Exception as exc:
                status = "error"
                summary = str(exc)[:500]
                asyncio.ensure_future(write_audit(agent_name, fn.__name__, params, summary, status))
                raise

            asyncio.ensure_future(write_audit(agent_name, fn.__name__, params, summary, status))
            return result

        return wrapper
    return decorator
