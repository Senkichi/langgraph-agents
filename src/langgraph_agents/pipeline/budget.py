"""Cost and wall-clock guard rails.

``over_budget`` is a pure function a router node can call to decide whether a
run should terminate. Both ceilings live on the run state (populated from
``RunConfig``) so different runs in the eval matrix can use different caps
without mutating module globals.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Mapping


def over_budget(state: Mapping) -> tuple[bool, str]:
    """Return ``(hit, reason)`` — reason is one of ``""``, ``"cost"``, ``"timeout"``.

    A missing or zero ceiling is treated as "no cap for this dimension" so
    smoke tests and trivial configurations can leave either ceiling unset.
    """
    cost_cap = float(state.get("max_total_cost_usd") or 0.0)
    if cost_cap > 0 and float(state.get("total_cost_usd") or 0.0) >= cost_cap:
        return True, "cost"

    wall_cap = int(state.get("max_wall_clock_seconds") or 0)
    start_iso = state.get("run_start_time")
    if wall_cap > 0 and start_iso:
        try:
            start_ts = datetime.fromisoformat(start_iso).timestamp()
        except ValueError:
            return False, ""
        if time.time() - start_ts > wall_cap:
            return True, "timeout"

    return False, ""


def elapsed_seconds(state: Mapping) -> float:
    """Seconds since ``run_start_time``. ``0.0`` if the timestamp is missing."""
    start_iso = state.get("run_start_time")
    if not start_iso:
        return 0.0
    try:
        start_ts = datetime.fromisoformat(start_iso).timestamp()
    except ValueError:
        return 0.0
    return max(0.0, time.time() - start_ts)
