"""Load a scenario YAML file into zone runs, leaks, and Wi-Fi outages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ZoneRun:
    at: datetime
    zone: int
    minutes: float
    gpm: float

    @property
    def end(self) -> datetime:
        return self.at + timedelta(minutes=self.minutes)


@dataclass(frozen=True)
class Leak:
    at: datetime
    gpm: float
    location: str


@dataclass(frozen=True)
class WifiOutage:
    at: datetime
    minutes: float

    @property
    def end(self) -> datetime:
        return self.at + timedelta(minutes=self.minutes)


@dataclass(frozen=True)
class Fault:
    at: datetime
    sensor: str
    mode: str
    minutes: float

    @property
    def end(self) -> datetime:
        return self.at + timedelta(minutes=self.minutes)


@dataclass(frozen=True)
class Reboot:
    at: datetime


@dataclass(frozen=True)
class Scenario:
    name: str
    device: str
    start: datetime
    end: datetime
    speed: float
    seed: int | None
    cut_in_psi: float
    cut_out_psi: float
    zone_runs: tuple[ZoneRun, ...]
    leaks: tuple[Leak, ...]
    outages: tuple[WifiOutage, ...]
    faults: tuple[Fault, ...]
    reboots: tuple[Reboot, ...]
    expect: dict


def load_scenario(path: Path) -> Scenario:
    raw = yaml.safe_load(path.read_text())
    start = datetime.fromisoformat(raw["start"])
    end = datetime.fromisoformat(raw["end"])
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError(f"{path}: start and end need a timezone offset")
    if end <= start:
        raise ValueError(f"{path}: end must be after start")

    switch = raw["system"]["pressure_switch"]
    zone_gpm = {int(zone): float(spec["gpm"]) for zone, spec in raw["system"]["zones"].items()}
    runs, leaks, outages, faults, reboots = _timeline(raw.get("timeline") or [], start, zone_gpm, path)
    return Scenario(
        name=str(raw["name"]),
        device=str(raw.get("device", "twin1")),
        start=start,
        end=end,
        speed=float(raw.get("speed", 0)),
        seed=None if raw.get("seed") is None else int(raw["seed"]),
        cut_in_psi=float(switch["cut_in"]),
        cut_out_psi=float(switch["cut_out"]),
        zone_runs=tuple(runs),
        leaks=tuple(leaks),
        outages=tuple(outages),
        faults=tuple(faults),
        reboots=tuple(reboots),
        expect=raw.get("expect") or {},
    )


def clock_ms(start: datetime, hhmm: str, not_before_ms: int | None = None) -> int:
    """Scenario clock time on `start`'s date, rolling forward a day when it would move backwards."""
    clock = datetime.strptime(hhmm, "%H:%M").time()
    at = datetime.combine(start.date(), clock, tzinfo=start.tzinfo)
    if at < start:
        at += timedelta(days=1)
    if not_before_ms is not None and int(at.timestamp() * 1000) < not_before_ms:
        at += timedelta(days=1)
    return int(at.timestamp() * 1000)


def _timeline(timeline: list, start: datetime, zone_gpm: dict[int, float], path: Path):
    """Clock times roll onto the next day when they move backwards, per the scenario doc."""
    day = start.date()
    previous = start
    runs: list[ZoneRun] = []
    leaks: list[Leak] = []
    outages: list[WifiOutage] = []
    faults: list[Fault] = []
    reboots: list[Reboot] = []
    for item in timeline:
        clock = datetime.strptime(item["at"], "%H:%M").time()
        at = datetime.combine(day, clock, tzinfo=start.tzinfo)
        if at < previous:
            day += timedelta(days=1)
            at = datetime.combine(day, clock, tzinfo=start.tzinfo)
        previous = at
        commands = [key for key in item if key != "at"]
        if len(commands) != 1:
            raise ValueError(f"{path}: timeline item at {item['at']} needs one command")
        command = commands[0]
        args = item[command]
        if command == "zone_on":
            zone = int(args["zone"])
            if zone not in zone_gpm and "gpm" not in args:
                raise ValueError(f"{path}: zone {zone} has no gpm in system.zones")
            gpm = float(args["gpm"]) if "gpm" in args else zone_gpm[zone]
            runs.append(ZoneRun(at=at, zone=zone, minutes=float(args["minutes"]), gpm=gpm))
        elif command == "leak":
            location = args.get("location", "downstream")
            if location not in ("upstream", "downstream"):
                raise ValueError(f"{path}: leak location {location}")
            leaks.append(Leak(at=at, gpm=float(args["gpm"]), location=location))
        elif command == "wifi_down":
            minutes = float(args["minutes"])
            if minutes <= 0:
                raise ValueError(f"{path}: wifi_down minutes must be positive")
            outages.append(WifiOutage(at=at, minutes=minutes))
        elif command == "fault":
            sensor = str(args["sensor"])
            mode = str(args["mode"])
            if sensor not in ("psi", "amps", "flow"):
                raise ValueError(f"{path}: fault sensor {sensor}")
            if mode != "disconnected":
                raise NotImplementedError(f"{path}: fault mode {mode} is not implemented yet")
            minutes = float(args["minutes"])
            if minutes <= 0:
                raise ValueError(f"{path}: fault minutes must be positive")
            faults.append(Fault(at=at, sensor=sensor, mode=mode, minutes=minutes))
        elif command == "reboot":
            reboots.append(Reboot(at=at))
        else:
            raise NotImplementedError(f"{path}: {command} is not implemented yet")
    return runs, leaks, outages, faults, reboots
