"""Check captured events against a scenario `expect` block."""

from __future__ import annotations

from bfwp_twin.scenario import Scenario, clock_ms


def check_expect(scenario: Scenario, events: list[dict]) -> None:
    """Raise AssertionError when a required event is missing or a forbidden one appears.

    `between` is inclusive. `after` is strict, so an event timestamped on the
    clock minute itself is not "after" that minute.
    """
    by_type: dict[str, list[int]] = {}
    for event in events:
        by_type.setdefault(event["type"], []).append(event["ts"])

    missing = []
    for spec in scenario.expect.get("events") or []:
        times = by_type.get(spec["type"], [])
        if "between" in spec:
            lo = clock_ms(scenario.start, spec["between"][0])
            hi = clock_ms(scenario.start, spec["between"][1], not_before_ms=lo)
            if not any(lo <= ts <= hi for ts in times):
                missing.append(
                    f"{spec['type']} between {spec['between'][0]} and {spec['between'][1]} (saw {times})"
                )
        elif "after" in spec:
            cut = clock_ms(scenario.start, spec["after"])
            if not any(ts > cut for ts in times):
                missing.append(f"{spec['type']} after {spec['after']} (saw {times})")
        else:
            missing.append(f"{spec['type']} needs between or after")
    if missing:
        raise AssertionError("missing events: " + "; ".join(missing))

    forbidden = []
    for spec in scenario.expect.get("no_events") or []:
        times = by_type.get(spec["type"], [])
        if "after" in spec:
            cut = clock_ms(scenario.start, spec["after"])
            hit = [ts for ts in times if ts > cut]
        elif "between" in spec:
            lo = clock_ms(scenario.start, spec["between"][0])
            hi = clock_ms(scenario.start, spec["between"][1], not_before_ms=lo)
            hit = [ts for ts in times if lo <= ts <= hi]
        else:
            hit = times
        if hit:
            forbidden.append(f"{spec['type']} at {hit}")
    if forbidden:
        raise AssertionError("forbidden events: " + "; ".join(forbidden))


def check_cadence(scenario: Scenario, telemetry: list[dict]) -> None:
    """Check publishing mode over scenario windows.

    `between` applies to samples strictly inside the window, so a reading
    timestamped on the opening minute stays with the previous span.
    `after` is strict. `report_on_change` requires two idle readings after
    that time less than 60 s apart.
    """
    for spec in scenario.expect.get("cadence") or []:
        if spec.get("report_on_change"):
            cut = clock_ms(scenario.start, spec["after"])
            times = sorted(row["ts"] for row in telemetry if row["ts"] > cut and row["mode"] == "idle")
            gaps = [later - earlier for earlier, later in zip(times, times[1:])]
            if not any(gap < 60_000 for gap in gaps):
                raise AssertionError(f"no idle report-on-change after {spec['after']} (gaps {gaps[:8]})")
            continue
        mode = spec["mode"]
        if "between" in spec:
            lo = clock_ms(scenario.start, spec["between"][0])
            hi = clock_ms(scenario.start, spec["between"][1], not_before_ms=lo)
            selected = [row for row in telemetry if lo < row["ts"] < hi]
            label = f"{mode} between {spec['between'][0]} and {spec['between'][1]}"
        elif "after" in spec:
            cut = clock_ms(scenario.start, spec["after"])
            selected = [row for row in telemetry if row["ts"] > cut]
            label = f"{mode} after {spec['after']}"
        else:
            raise AssertionError(f"cadence spec needs between, after, or report_on_change: {spec}")
        if not selected:
            raise AssertionError(f"no telemetry for {label}")
        bad = [row["ts"] for row in selected if row["mode"] != mode]
        if bad:
            raise AssertionError(f"expected {label}; other modes at {bad[:8]}")
