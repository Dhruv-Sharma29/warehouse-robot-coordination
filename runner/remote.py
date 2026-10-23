"""Local vs remote inference for the learned travel-time model, with injected faults (SPEC.md § optional
systems extension). Simulated systems behaviour, not real robot offloading.

    python -m runner.remote            # writes results/summary/remote_inference.json

Same held-out scenarios for every condition (paired, sequential so the seeded drops land on the
same requests every run):
  local-mlp      the MLP in process (as in runner.experiment)
  remote         the same MLP behind predictor/serve.py, no faults: must match local exactly
  remote-slow    every reply 250 ms late against a 100 ms budget: falls back to the heuristic
  remote-lossy   20 % of connections dropped
  heuristic      the fallback on its own, for reference
"""

from __future__ import annotations

import json
import statistics
import threading
import time
from pathlib import Path

from planners.policies import HeuristicPolicy, LearnedPolicy
from planners.remote import RemotePolicy
from predictor.model import TravelTimeModel
from predictor.serve import serve
from runner.experiment import scenario
from sim.engine import Simulation
from sim.layout import HELDOUT_FAMILIES

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "results/models/mlp.json"
SCENARIOS = [(f, s, 20, regime) for f in sorted(HELDOUT_FAMILIES) for regime in ("moderate", "saturated")
             for s in (1, 2, 3, 4, 5)]
REMOTE = {"remote": (0.0, 0.0), "remote-slow": (250.0, 0.0), "remote-lossy": (0.0, 0.2)}
PORT = 18080


def run(policy, sc_args) -> dict:
    t0 = time.perf_counter()
    m = Simulation(scenario(*sc_args), policy).run()
    return {"jobs_completed": m["jobs_completed"], "cycle_mean": m["cycle_mean"], "collisions": m["collisions"],
            "wall_s": round(time.perf_counter() - t0, 2)}


def main() -> None:
    results = {"scenarios": [list(s) for s in SCENARIOS], "model": str(MODEL.relative_to(ROOT)),
               "budget_ms": 100, "circuit": {"trip": 3, "cooldown_calls": 50}, "conditions": {}}
    local = TravelTimeModel.load(MODEL)
    for name, make in (("local-mlp", lambda: LearnedPolicy(local)), ("heuristic", HeuristicPolicy)):
        results["conditions"][name] = {"runs": [run(make(), s) for s in SCENARIOS]}
    for i, (name, (latency_ms, drop)) in enumerate(REMOTE.items()):
        server = serve(MODEL, PORT + i, latency_ms, drop, seed=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            runs, stats = [], {"remote": 0, "fallback": 0, "failed_calls": 0, "circuit_opened": 0}
            for s in SCENARIOS:
                pol = RemotePolicy(f"http://127.0.0.1:{PORT + i}/predict", budget_s=0.1)
                runs.append(run(pol, s))
                stats = {k: stats[k] + pol.stats[k] for k in stats}
            results["conditions"][name] = {"latency_ms": latency_ms, "drop_rate": drop, "runs": runs, "calls": stats,
                                           "fallback_share": round(stats["fallback"] / max(1, stats["remote"] + stats["fallback"]), 3)}
        finally:
            server.shutdown()
            server.server_close()
    for c in results["conditions"].values():
        c["jobs_completed_mean"] = round(statistics.mean(r["jobs_completed"] for r in c["runs"]), 2)
        c["collisions"] = sum(r["collisions"] for r in c["runs"])
        c["wall_s_mean"] = round(statistics.mean(r["wall_s"] for r in c["runs"]), 2)
    loc = [r["jobs_completed"] for r in results["conditions"]["local-mlp"]["runs"]]
    results["remote_matches_local"] = [r["jobs_completed"] for r in results["conditions"]["remote"]["runs"]] == loc
    out = ROOT / "results/summary/remote_inference.json"
    out.write_text(json.dumps(results, indent=1) + "\n")
    print(json.dumps({k: {kk: v.get(kk) for kk in ("jobs_completed_mean", "fallback_share", "collisions", "wall_s_mean")}
                      for k, v in results["conditions"].items()}, indent=1))
    print("remote matches local:", results["remote_matches_local"])


if __name__ == "__main__":
    main()
