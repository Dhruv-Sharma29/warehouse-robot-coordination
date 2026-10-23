"""Remote predictor: healthy service gives the local model's estimates; a slow or dropping service
falls back to the heuristic, and the circuit breaker stops calling a failing service."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from planners.policies import HeuristicPolicy, LearnedPolicy
from planners.remote import RemotePolicy
from predictor.model import TravelTimeModel
from predictor.serve import serve
from runner.experiment import scenario
from sim.engine import Simulation
from sim.layout import HELDOUT_FAMILIES

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "results/models/mlp.json"


@pytest.fixture
def service(request):
    latency_ms, drop = request.param
    server = serve(MODEL, 0, latency_ms, drop, seed=0)       # port 0: any free port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/predict"
    server.shutdown()
    server.server_close()


def sim_and_pairs():
    sim = Simulation(scenario(sorted(HELDOUT_FAMILIES)[0], 1, 20, "moderate"), HeuristicPolicy())
    robots = sim.active_robots()[:4]
    return sim, [(r, s) for r in robots for s in sim.layout.stations]


@pytest.mark.parametrize("service", [(0.0, 0.0)], indirect=True)
def test_healthy_service_returns_the_local_models_estimates(service):
    sim, pairs = sim_and_pairs()
    remote = RemotePolicy(service, budget_s=2.0)
    assert remote.costs(sim, pairs) == LearnedPolicy(TravelTimeModel.load(MODEL)).costs(sim, pairs)
    assert remote.stats["remote"] == 1 and remote.stats["fallback"] == 0


@pytest.mark.parametrize("service", [(300.0, 0.0), (0.0, 1.0)], indirect=True)
def test_slow_or_dropping_service_falls_back_and_trips_the_circuit(service):
    sim, pairs = sim_and_pairs()
    remote = RemotePolicy(service, budget_s=0.05, trip=3, cooldown=5)
    expected = HeuristicPolicy().costs(sim, pairs)
    for _ in range(10):
        assert remote.costs(sim, pairs) == expected
    # 3 failed calls open the circuit, 5 skipped, then 2 more failures before the 10th: 5 calls, 5 skips
    assert remote.stats == {"remote": 0, "fallback": 10, "failed_calls": 5, "circuit_opened": 1}
