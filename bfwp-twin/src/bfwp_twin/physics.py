"""Well-house physical model.

Boyle's law on the tank air charge, a pressure switch, a straight-line pump
curve, and zone demand scaled by sqrt(psi / nominal). Simulation step is 100 ms.
This module does not publish MQTT or emit device events.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bfwp_twin.scenario import Scenario, load_scenario

# Gauge pressures. Boyle's law uses absolute pressure.
ATM_PSI = 14.696
TANK_GALLONS = 86.0
PRECHARGE_PSI = 38.0
# Scenario zone gpm values are the demand at this pressure.
NOMINAL_PSI = 50.0
# Straight line from (0 psi, Q) to (shutoff, 0). Chosen so a 14 gpm zone
# still refills the tank up to a 60 psi cut-out. Not a contract value.
PUMP_GPM_AT_0_PSI = 55.0
PUMP_SHUTOFF_PSI = 90.0
STEP_MS = 100
SAMPLE_MS = 1000


@dataclass(frozen=True)
class PhysicsRun:
    truth_log_path: Path
    samples: tuple[tuple[int, float], ...]
    """(simulated epoch ms, tank psi) once per second."""


def water_gallons(psi_gauge: float) -> float:
    """Water in the tank when the air charge is at this gauge pressure."""
    air = (PRECHARGE_PSI + ATM_PSI) * TANK_GALLONS / (psi_gauge + ATM_PSI)
    return TANK_GALLONS - air


def psi_gauge(water_gal: float) -> float:
    air = max(TANK_GALLONS - water_gal, 0.05)
    absolute = (PRECHARGE_PSI + ATM_PSI) * TANK_GALLONS / air
    return absolute - ATM_PSI


def run_scenario(path: Path, truth_log_dir: Path | None = None) -> PhysicsRun:
    scenario = load_scenario(path)
    return run_physics(scenario, truth_log_dir=truth_log_dir)


def run_physics(scenario: Scenario, truth_log_dir: Path | None = None, observer=None) -> PhysicsRun:
    if scenario.cut_out_psi <= scenario.cut_in_psi:
        raise ValueError("cut_out must be above cut_in")

    log_dir = truth_log_dir or Path(__file__).resolve().parents[2] / "truth-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{scenario.name}-{uuid.uuid4().hex[:12]}.jsonl"

    start_ms = _epoch_ms(scenario.start)
    end_ms = _epoch_ms(scenario.end)
    runs = tuple(
        (_epoch_ms(run.at), _epoch_ms(run.end), run)
        for run in scenario.zone_runs
    )
    leak_starts = tuple((_epoch_ms(leak.at), leak) for leak in scenario.leaks)
    injections = tuple(sorted(
        [(_epoch_ms(run.at), "zone_on", run) for run in scenario.zone_runs]
        + [(_epoch_ms(leak.at), "leak", leak) for leak in scenario.leaks]
        + [(_epoch_ms(out.at), "wifi_down", out) for out in scenario.outages]
        + [(_epoch_ms(fault.at), "fault", fault) for fault in scenario.faults]
        + [(_epoch_ms(reboot.at), "reboot", reboot) for reboot in scenario.reboots]
    ))

    water = water_gallons(scenario.cut_out_psi)
    pump_on = False
    samples: list[tuple[int, float]] = []
    lines: list[str] = []
    next_inject = 0

    t_ms = start_ms
    next_sample = start_ms
    while t_ms < end_ms:
        while next_inject < len(injections) and t_ms >= injections[next_inject][0]:
            lines.append(_truth_line(injections[next_inject]))
            next_inject += 1

        psi = psi_gauge(water)
        if (not pump_on) and psi <= scenario.cut_in_psi:
            pump_on = True
        elif pump_on and psi >= scenario.cut_out_psi:
            pump_on = False

        demand = 0.0
        for start, end, run in runs:
            if start <= t_ms < end:
                demand += _orifice_gpm(run.gpm, psi)
        leak_gpm = 0.0
        leak_location = None
        for start, leak in leak_starts:
            if t_ms >= start:
                leak_gpm = _orifice_gpm(leak.gpm, psi)
                leak_location = leak.location
        metered = demand + (leak_gpm if leak_location == "downstream" else 0.0)
        supply = 0.0
        if pump_on and psi < PUMP_SHUTOFF_PSI:
            supply = PUMP_GPM_AT_0_PSI * (1.0 - psi / PUMP_SHUTOFF_PSI)
        if observer is not None:
            observer(t_ms, psi, pump_on, metered)

        water += (supply - demand - leak_gpm) * (STEP_MS / 60_000.0)
        water = min(max(water, 0.0), TANK_GALLONS - 0.05)

        if t_ms >= next_sample:
            samples.append((t_ms, psi_gauge(water)))
            next_sample += SAMPLE_MS
        t_ms += STEP_MS

    log_path.write_text("\n".join(lines) + ("\n" if lines else ""))
    return PhysicsRun(truth_log_path=log_path, samples=tuple(samples))


def _orifice_gpm(gpm_at_nominal: float, psi: float) -> float:
    if psi <= 0:
        return 0.0
    return gpm_at_nominal * (psi / NOMINAL_PSI) ** 0.5


def _truth_line(injection) -> str:
    _ts, kind, payload = injection
    if kind == "zone_on":
        body = {
            "ts": _epoch_ms(payload.at),
            "inject": "zone_on",
            "zone": payload.zone,
            "minutes": payload.minutes,
            "gpm": payload.gpm,
        }
    elif kind == "wifi_down":
        body = {
            "ts": _epoch_ms(payload.at),
            "inject": "wifi_down",
            "minutes": payload.minutes,
        }
    elif kind == "fault":
        body = {
            "ts": _epoch_ms(payload.at),
            "inject": "fault",
            "sensor": payload.sensor,
            "mode": payload.mode,
            "minutes": payload.minutes,
        }
    elif kind == "reboot":
        body = {
            "ts": _epoch_ms(payload.at),
            "inject": "reboot",
        }
    else:
        body = {
            "ts": _epoch_ms(payload.at),
            "inject": "leak",
            "gpm": payload.gpm,
            "location": payload.location,
        }
    return json.dumps(body, separators=(",", ":"))


def _epoch_ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def drawdown_gallons(low_psi: float, high_psi: float) -> float:
    return water_gallons(high_psi) - water_gallons(low_psi)
