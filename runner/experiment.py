"""Closed-loop paired comparison of assignment policies (PLAN.md M5/M6).

    python -m runner.experiment tune-heuristic      # pick heuristic weights on training layouts
    python -m runner.experiment compare             # held-out layouts, all policies, paired

Every policy runs on the identical scenario (layout, orders, fleet, faults, seed): the
comparison is paired. Reported per policy: mean of each metric, and the paired difference vs the
distance baseline with a 95% t-interval and win/loss counts. The WHCA* router, safety layer and
order streams are the same for all policies; only the travel-time estimate behind assignment and
station choice changes.
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
from multiprocessing import Pool
from pathlib import Path

from planners.policies import DistancePolicy, HeuristicPolicy, LearnedPolicy
from predictor.model import TravelTimeModel
from sim.engine import Simulation
from sim.layout import HELDOUT_FAMILIES, TRAIN_FAMILIES, spec
from sim.scenario import Scenario, with_faults

ROOT = Path(__file__).resolve().parents[1]
HORIZON = 1000
REGIMES = {"moderate": {20: 0.30, 40: 0.50}, "saturated": {20: 1.0, 40: 1.0}}
METRICS = ["jobs_completed", "cycle_mean", "cycle_p95", "urgent_missed", "moves", "safety_interventions",
           "stuck_episodes", "planner_s"]
T95 = {9: 2.262, 19: 2.093, 39: 2.023, 79: 1.990}  # two-sided 95% t quantiles by degrees of freedom
HIGHER_IS_BETTER = {"jobs_completed"}  # every other metric: lower is better


def scenario(family: str, seed: int, n_robots: int, regime: str) -> Scenario:
    rate = REGIMES[regime][n_robots] if regime in REGIMES else 3.0  # "scaling": saturate any fleet
    sc = Scenario(spec(family, seed), n_robots=n_robots, horizon=HORIZON, order_rate=rate, seed=seed * 100 + n_robots)
    return with_faults(sc)


def make_policy(name: str, params: dict):
    if name == "distance":
        return DistancePolicy()
    if name == "heuristic":
        return HeuristicPolicy(**params.get("heuristic", {}))
    if name.startswith("learned"):
        return LearnedPolicy(TravelTimeModel.load(ROOT / "results/models" / f"{name.split('-')[1]}.json"))
    raise ValueError(name)


def run_one(job: dict) -> dict:
    sc = scenario(job["family"], job["seed"], job["n_robots"], job["regime"])
    m = Simulation(sc, make_policy(job["policy"], job.get("params", {})), router_mode=job.get("router", "rolling")).run()
    return {**{k: job[k] for k in ("family", "seed", "n_robots", "regime", "policy")}, **m}


def paired(rows: list[dict], policy: str, metric: str, base: str = "distance") -> dict:
    key = lambda r: (r["family"], r["seed"], r["n_robots"], r["regime"])  # noqa: E731
    b = {key(r): r[metric] for r in rows if r["policy"] == base}
    diffs = [r[metric] - b[key(r)] for r in rows if r["policy"] == policy and r[metric] is not None and b.get(key(r)) is not None]
    if len(diffs) < 2:
        return {}
    mean, sd = statistics.mean(diffs), statistics.stdev(diffs)
    half = T95.get(len(diffs) - 1, 1.96) * sd / len(diffs) ** 0.5
    sign = 1 if metric in HIGHER_IS_BETTER else -1  # "better" respects each metric's direction
    return {"n": len(diffs), "mean_diff": round(mean, 2), "ci95": [round(mean - half, 2), round(mean + half, 2)],
            "better": sum(sign * d > 0 for d in diffs), "worse": sum(sign * d < 0 for d in diffs),
            "ties": sum(d == 0 for d in diffs)}


def tune_heuristic(workers: int) -> dict:
    grid = list(itertools.product([0.0, 1.0, 2.0, 4.0], [0.0, 3.0, 6.0, 12.0]))
    scen = [(f, s, n, reg) for f in sorted(TRAIN_FAMILIES) for s in (401, 402) for n in (20, 40) for reg in REGIMES]
    jobs = [{"family": f, "seed": s, "n_robots": n, "regime": reg, "policy": "heuristic",
             "params": {"heuristic": {"per_robot": a, "per_queued": q}}, "grid": (a, q)}
            for (a, q) in grid for (f, s, n, reg) in scen]
    with Pool(workers) as pool:
        rows = pool.map(run_one, jobs)
    score = {}
    for job, row in zip(jobs, rows):
        score.setdefault(job["grid"], []).append(row["jobs_completed"])
    (a, q), best = max(score.items(), key=lambda kv: statistics.mean(kv[1]))
    out = {"per_robot": a, "per_queued": q, "mean_jobs_completed": statistics.mean(best),
           "grid": {f"{k[0]},{k[1]}": statistics.mean(v) for k, v in score.items()}}
    (ROOT / "results/summary/heuristic_tuning.json").write_text(json.dumps(out, indent=1))
    return out


def router_ablation(workers: int) -> dict:
    """Clear vs rolling WHCA* rounds, heuristic policy, training layouts (not held-out)."""
    tuned = {"per_robot": 4.0, "per_queued": 3.0}
    jobs = [{"family": f, "seed": s, "n_robots": n, "regime": "saturated", "policy": "heuristic",
             "params": {"heuristic": tuned}, "router": mode}
            for mode in ("clear", "rolling") for f in sorted(TRAIN_FAMILIES) for s in (401, 402, 403) for n in (20, 40)]
    with Pool(workers) as pool:
        rows = pool.map(run_one, jobs)
    out = {}
    for mode in ("clear", "rolling"):
        sub = [r for job, r in zip(jobs, rows) if job["router"] == mode]
        out[mode] = {m: round(statistics.mean(r[m] for r in sub), 2)
                     for m in ("jobs_completed", "safety_interventions", "stuck_episodes", "planner_s")}
    out["runs_per_mode"] = len(jobs) // 2
    (ROOT / "results/summary/router_ablation.json").write_text(json.dumps(out, indent=1))
    return out


def scaling(workers: int) -> dict:
    """Fleet size 20 -> 100 on the XL layout, tuned heuristic, saturated: planner cost and throughput."""
    tuned = json.loads((ROOT / "results/summary/heuristic_tuning.json").read_text())
    params = {"heuristic": {"per_robot": tuned["per_robot"], "per_queued": tuned["per_queued"]}}
    jobs = [{"family": "xl-14x6", "seed": s, "n_robots": n, "regime": "scaling", "policy": "heuristic", "params": params}
            for n in (20, 50, 100) for s in (501, 502, 503)]
    with Pool(workers) as pool:
        rows = pool.map(run_one, jobs)
    out = {}
    for n in (20, 50, 100):
        sub = [r for r in rows if r["n_robots"] == n]
        out[n] = {m: round(statistics.mean(r[m] for r in sub), 2) for m in
                  ("jobs_completed", "safety_interventions", "stuck_episodes", "robots_stuck_at_end", "planner_s", "plan_ms_p95")}
        out[n]["jobs_per_robot"] = round(out[n]["jobs_completed"] / n, 2)
    (ROOT / "results/summary/scaling.json").write_text(json.dumps(out, indent=1))
    return out


def compare(workers: int, families: dict, seeds: range, policies: list[str], label: str) -> dict:
    tuned = json.loads((ROOT / "results/summary/heuristic_tuning.json").read_text())
    params = {"heuristic": {"per_robot": tuned["per_robot"], "per_queued": tuned["per_queued"]}}
    jobs = [{"family": f, "seed": s, "n_robots": n, "regime": reg, "policy": p, "params": params}
            for f in sorted(families) for s in seeds for n in (20, 40) for reg in REGIMES for p in policies]
    with Pool(workers) as pool:
        rows = pool.map(run_one, jobs)
    (ROOT / f"results/raw/compare_{label}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return summarize(label, policies, params["heuristic"])


def summarize(label: str, policies: list[str], heuristic_params: dict) -> dict:
    """Build the summary from saved raw rows (re-runnable without re-simulating)."""
    rows = [json.loads(line) for line in (ROOT / f"results/raw/compare_{label}.jsonl").read_text().splitlines()]
    summary = {"label": label, "scenarios": len(rows) // len(policies), "heuristic_params": heuristic_params,
               "by_regime": {}}
    for reg in REGIMES:
        sub = [r for r in rows if r["regime"] == reg]
        summary["by_regime"][reg] = {
            p: {"mean": {m: round(statistics.mean(r[m] for r in sub if r["policy"] == p and r[m] is not None), 2) for m in METRICS},
                "vs_distance": {m: paired(sub, p, m) for m in METRICS} if p != "distance" else None,
                # the tuned heuristic is the strong classical baseline; the claim rests on this comparison
                "vs_heuristic": {m: paired(sub, p, m, base="heuristic") for m in METRICS}
                if p.startswith("learned") else None}
            for p in policies}
    (ROOT / f"results/summary/compare_{label}.json").write_text(json.dumps(summary, indent=1))
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=["router-ablation", "tune-heuristic", "compare", "compare-train", "scaling",
                                    "compare-aggregated"])
    p.add_argument("--workers", type=int, default=10)
    args = p.parse_args()
    (ROOT / "results/summary").mkdir(parents=True, exist_ok=True)
    policies = ["distance", "heuristic", "learned-mlp", "learned-ridge"]
    if args.mode == "compare-aggregated":
        # Same 80 held-out scenarios as "compare"; adds the model retrained on its own trips (round 1).
        s = compare(args.workers, HELDOUT_FAMILIES, range(201, 211),
                    ["distance", "heuristic", "learned-mlp", "learned-mlp_r1"], "heldout-aggregated")
        print(json.dumps(s["by_regime"], indent=1))
    elif args.mode == "scaling":
        print(json.dumps(scaling(args.workers), indent=1))
    elif args.mode == "router-ablation":
        print(json.dumps(router_ablation(args.workers), indent=1))
    elif args.mode == "tune-heuristic":
        print(json.dumps(tune_heuristic(args.workers), indent=1))
    elif args.mode == "compare":
        s = compare(args.workers, HELDOUT_FAMILIES, range(201, 211), policies, "heldout")
        print(json.dumps(s["by_regime"], indent=1))
    else:
        s = compare(args.workers, TRAIN_FAMILIES, range(301, 306), policies, "train-families")
        print(json.dumps(s["by_regime"], indent=1))


if __name__ == "__main__":
    main()
