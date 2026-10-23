"""Statistics and data-hygiene tests for the experiment pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from runner.experiment import paired

ROOT = Path(__file__).resolve().parents[1]


def rows(metric, base_vals, pol_vals):
    out = []
    for i, (b, p) in enumerate(zip(base_vals, pol_vals)):
        common = {"family": "f", "seed": i, "n_robots": 20, "regime": "r"}
        out += [{**common, "policy": "base", metric: b}, {**common, "policy": "new", metric: p}]
    return out


def test_paired_better_respects_metric_direction():
    # Regression: "better" once meant "larger" for every metric, inverting it for cycle times.
    up = paired(rows("jobs_completed", [10, 10, 10], [12, 11, 9]), "new", "jobs_completed", base="base")
    assert (up["better"], up["worse"]) == (2, 1)
    down = paired(rows("cycle_p95", [50, 50, 50], [40, 45, 55]), "new", "cycle_p95", base="base")
    assert (down["better"], down["worse"]) == (2, 1) and down["mean_diff"] < 0


def test_paired_interval_contains_mean():
    r = paired(rows("jobs_completed", [10] * 5, [11, 13, 9, 12, 10]), "new", "jobs_completed", base="base")
    assert r["ci95"][0] <= r["mean_diff"] <= r["ci95"][1]


DATA = ROOT / "results/data"


@pytest.mark.skipif(not (DATA / "train.npz").exists(), reason="run python -m predictor.dataset first")
def test_held_out_layouts_never_reach_training_data():
    from sim.layout import HELDOUT_FAMILIES
    for split in ("train", "val"):
        fams = set(np.load(DATA / f"{split}.npz")["family"].tolist())
        assert not fams & set(HELDOUT_FAMILIES), split
    assert set(np.load(DATA / "heldout.npz")["family"].tolist()) <= set(HELDOUT_FAMILIES)


@pytest.mark.skipif(not (ROOT / "results/models/mlp.json").exists(), reason="train first")
def test_saved_model_reloads_with_identical_predictions():
    from predictor.features import FEATURES
    from predictor.model import TravelTimeModel
    d = np.load(DATA / "val.npz")
    rows_ = [dict(zip(FEATURES, x)) for x in d["X"][:200]]
    m = TravelTimeModel.load(ROOT / "results/models/mlp.json")
    tmp = ROOT / "results/models/_roundtrip.json"
    m.save(tmp)
    try:
        assert np.array_equal(m.predict(rows_), TravelTimeModel.load(tmp).predict(rows_))
    finally:
        tmp.unlink()
