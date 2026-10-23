"""Collect trip data (decision-time features + realised travel time) from baseline runs.

    python -m predictor.dataset --workers 8

Splits are decided by layout family and seed before any data exists:
  train    training families, seeds 1-6
  val      training families, seeds 7-8  (early stopping, model selection)
  heldout  held-out families, seeds 101-104 (accuracy only; never used for training or selection)
Data comes from the distance-policy baseline. When the learned policy is in charge, trips
are different (distribution shift); the closed-loop evaluation is what decides whether it helps.
"""

from __future__ import annotations

import argparse
import itertools
import json
from multiprocessing import Pool
from pathlib import Path

import numpy as np

from planners.policies import DistancePolicy
from predictor.features import FEATURES
from sim.engine import Simulation
from sim.layout import HELDOUT_FAMILIES, TRAIN_FAMILIES, spec
from sim.scenario import Scenario, with_faults

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/data"
SPLITS = {"train": (TRAIN_FAMILIES, range(1, 7)), "val": (TRAIN_FAMILIES, range(7, 9)),
          "heldout": (HELDOUT_FAMILIES, range(101, 105))}
FLEETS, RATES, FAULTS, HORIZON = (15, 25, 35), (0.4, 0.8), (False, True), 800


def configs(split: str) -> list[dict]:
    families, seeds = SPLITS[split]
    return [{"family": f, "seed": s, "n_robots": n, "rate": r, "faults": fl}
            for f, s, n, r, fl in itertools.product(sorted(families), seeds, FLEETS, RATES, FAULTS)]


def collect(cfg: dict) -> list[dict]:
    sc = Scenario(spec(cfg["family"], cfg["seed"]), n_robots=cfg["n_robots"], horizon=HORIZON,
                  order_rate=cfg["rate"], seed=cfg["seed"] * 1000 + cfg["n_robots"] + int(cfg["rate"] * 10))
    if cfg["faults"]:
        sc = with_faults(sc)
    sim = Simulation(sc, DistancePolicy(), record_trips=True)
    sim.run()
    return [{**t, "family": cfg["family"], "seed": cfg["seed"]} for t in sim.trips]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workers", type=int, default=8)
    args = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for split in SPLITS:
        with Pool(args.workers) as pool:
            trips = [t for chunk in pool.map(collect, configs(split)) for t in chunk]
        X = np.array([[t[f] for f in FEATURES] for t in trips], dtype=np.float64)
        y = np.array([t["actual"] for t in trips], dtype=np.float64)
        meta = {"split": split, "n": len(trips), "families": sorted({t["family"] for t in trips}),
                "seeds": sorted({t["seed"] for t in trips}), "features": FEATURES}
        np.savez_compressed(OUT / f"{split}.npz", X=X, y=y, kind=np.array([t["kind"] for t in trips]),
                            family=np.array([t["family"] for t in trips]))
        (OUT / f"{split}.meta.json").write_text(json.dumps(meta, indent=1))
        print(split, len(trips), "trips", meta["families"])


if __name__ == "__main__":
    main()
