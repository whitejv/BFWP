"""Physics check for baseline_normal_night. No MQTT."""

import json
from datetime import timedelta
from pathlib import Path

from bfwp_twin.physics import drawdown_gallons, run_scenario
from bfwp_twin.scenario import load_scenario

REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "bfwp-spec" / "contracts" / "scenarios" / "baseline_normal_night.yaml"


def test_tank_drawdown_is_about_22_gallons():
    # Spec: 86 gal tank, 38 psi pre-charge, about 22 gal from 40 psi to 60 psi.
    assert abs(drawdown_gallons(40, 60) - 22) < 1


def test_baseline_normal_night_cycles_between_cut_in_and_cut_out(tmp_path):
    scenario = load_scenario(SCENARIO)
    result = run_scenario(SCENARIO, truth_log_dir=tmp_path)

    rows = [json.loads(line) for line in result.truth_log_path.read_text().splitlines()]
    assert [(row["inject"], row["zone"], row["minutes"], row["gpm"]) for row in rows] == [
        ("zone_on", 1, 15, 14),
        ("zone_on", 2, 15, 11),
        ("zone_on", 3, 15, 12),
    ]
    assert [row["ts"] for row in rows] == [
        int(run.at.timestamp() * 1000) for run in scenario.zone_runs
    ]

    watering_start = int(scenario.zone_runs[0].at.timestamp() * 1000)
    watering_end = int(scenario.zone_runs[-1].end.timestamp() * 1000)
    during = [psi for ts, psi in result.samples if watering_start <= ts < watering_end]
    assert min(during) <= scenario.cut_in_psi + 0.5
    assert max(during) >= scenario.cut_out_psi - 0.5

    # A cycle: cut-out is reached, then pressure falls back to cut-in while a zone is still drawing.
    saw_high = False
    fell_back = False
    for psi in during:
        if psi >= scenario.cut_out_psi - 0.5:
            saw_high = True
        elif saw_high and psi <= scenario.cut_in_psi + 0.5:
            fell_back = True
            break
    assert saw_high and fell_back

    hold_at = watering_end + int(timedelta(minutes=1).total_seconds() * 1000)
    after = [psi for ts, psi in result.samples if ts >= hold_at]
    assert max(after) - min(after) < 0.5
