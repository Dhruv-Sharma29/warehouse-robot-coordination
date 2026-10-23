"""Train travel-time predictors and report accuracy (PLAN.md M4).

    python -m predictor.train

Compared on validation (training families, unseen seeds) and held-out (unseen layout families):
  distance      prediction = shortest-path distance (what the classical baseline assumes)
  distance-fit  a * distance + b, least squares (calibrated, still congestion-blind)
  ridge         linear model on all decision-time features
  mlp           PyTorch 2x64 MLP, 3 seeds; the one with the best validation loss is saved
Reported: MAE overall, per trip kind, and on congested trips (actual >= 1.5x distance).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from predictor.features import FEATURES
from predictor.model import fit_mlp, fit_ridge

ROOT = Path(__file__).resolve().parents[1]
DATA, MODELS = ROOT / "results/data", ROOT / "results/models"


def load(split: str):
    d = np.load(DATA / f"{split}.npz")
    rows = [dict(zip(FEATURES, x)) for x in d["X"]]
    return rows, d["y"], d["kind"], d["X"][:, FEATURES.index("dist")]


def report(pred: np.ndarray, y: np.ndarray, kind: np.ndarray, dist: np.ndarray) -> dict:
    err = np.abs(pred - y)
    congested = y >= 1.5 * np.maximum(dist, 1)
    return {"mae": round(float(err.mean()), 2),
            "mae_to_pickup": round(float(err[kind == "to_pickup"].mean()), 2),
            "mae_to_station": round(float(err[kind == "to_station"].mean()), 2),
            "mae_congested": round(float(err[congested].mean()), 2), "congested_share": round(float(congested.mean()), 3),
            "rank_corr_excess": round(float(np.corrcoef(np.argsort(np.argsort(pred - dist)),
                                                        np.argsort(np.argsort(y - dist)))[0, 1]), 3)}


def main() -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    tr_rows, tr_y, _, tr_d = load("train")
    splits = {s: load(s) for s in ("val", "heldout")}
    a, b = np.polyfit(tr_d, tr_y, 1)
    results = {"n_train": len(tr_y), "distance_fit": {"a": round(a, 3), "b": round(b, 2)}}
    for name, predict in [("distance", lambda rows, d: d), ("distance-fit", lambda rows, d: a * d + b)]:
        results[name] = {s: report(predict(r, d), y, k, d) for s, (r, y, k, d) in splits.items()}
    ridge = fit_ridge(tr_rows, tr_y)
    ridge.save(MODELS / "ridge.json")
    results["ridge"] = {s: report(ridge.predict(r), y, k, d) for s, (r, y, k, d) in splits.items()}
    best = None
    for seed in range(3):
        model, info = fit_mlp(tr_rows, tr_y, splits["val"][0], splits["val"][1], seed=seed)
        res = {s: report(model.predict(r), y, k, d) for s, (r, y, k, d) in splits.items()}
        results[f"mlp-seed{seed}"] = {**res, "train": info}
        if best is None or info["best_val_mse_log"] < best[1]:
            best = (model, info["best_val_mse_log"], seed)
    best[0].save(MODELS / "mlp.json")
    results["selected_mlp_seed"] = best[2]
    (ROOT / "results/summary").mkdir(parents=True, exist_ok=True)
    (ROOT / "results/summary/predictor.json").write_text(json.dumps(results, indent=1))
    for name in ("distance", "distance-fit", "ridge", "mlp-seed0", "mlp-seed1", "mlp-seed2"):
        v, h = results[name]["val"], results[name]["heldout"]
        print(f"{name:13} val MAE {v['mae']:6} congested {v['mae_congested']:6} | heldout MAE {h['mae']:6} "
              f"congested {h['mae_congested']:6} rank-corr(excess) {h['rank_corr_excess']}")


if __name__ == "__main__":
    main()
