"""Run the hydraulic model and the device, writing a truth log and a message file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bfwp_twin.device import Device
from bfwp_twin.physics import PhysicsRun, run_physics, run_scenario
from bfwp_twin.scenario import load_scenario


@dataclass(frozen=True)
class OfflineRun:
    physics: PhysicsRun
    messages_path: Path
    records: tuple[dict, ...]


def run_offline(path: Path, truth_log_dir: Path | None = None) -> OfflineRun:
    scenario = load_scenario(path)
    device = Device(scenario)
    physics = run_physics(scenario, truth_log_dir=truth_log_dir, observer=device.observe)
    messages_path = physics.truth_log_path.with_name(physics.truth_log_path.stem + ".messages.jsonl")
    device.write(messages_path)
    return OfflineRun(physics=physics, messages_path=messages_path, records=tuple(device.records))


def run_physics_only(path: Path, truth_log_dir: Path | None = None) -> PhysicsRun:
    return run_scenario(path, truth_log_dir=truth_log_dir)
