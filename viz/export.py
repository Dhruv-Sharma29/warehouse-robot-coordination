"""Side-by-side replay of two policies on the same scenario, as one self-contained HTML file.

    python -m viz.export --family wide-10x5 --seed 205 --robots 40 --regime saturated \\
        --left heuristic --right learned-mlp --out results/replay/demo.html
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from runner.experiment import make_policy, scenario
from sim.engine import Simulation

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = Path(__file__).with_name("replay.html")


def record(family: str, seed: int, robots: int, regime: str, policy: str) -> dict:
    tuned = json.loads((ROOT / "results/summary/heuristic_tuning.json").read_text())
    params = {"heuristic": {"per_robot": tuned["per_robot"], "per_queued": tuned["per_queued"]}}
    sim = Simulation(scenario(family, seed, robots, regime), make_policy(policy, params), record_replay=True)
    metrics = sim.run()
    done_at = sorted(j.done for j in sim.jobs if j.done is not None)
    return {"policy": policy, "metrics": metrics, "done_at": done_at, **sim.replay}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--family", default="wide-10x5")
    p.add_argument("--seed", type=int, default=205)
    p.add_argument("--robots", type=int, default=40)
    p.add_argument("--regime", default="saturated")
    p.add_argument("--left", default="distance")
    p.add_argument("--right", default="heuristic")
    p.add_argument("--out", type=Path, default=ROOT / "results/replay/demo.html")
    args = p.parse_args()
    runs = [record(args.family, args.seed, args.robots, args.regime, pol) for pol in (args.left, args.right)]
    data = {"title": f"{args.family} seed {args.seed}, {args.robots} robots, {args.regime}", "runs": runs}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(TEMPLATE.read_text().replace("/*DATA*/null", json.dumps(data, separators=(",", ":"))))
    print(args.out, {r["policy"]: r["metrics"]["jobs_completed"] for r in runs})


if __name__ == "__main__":
    main()
