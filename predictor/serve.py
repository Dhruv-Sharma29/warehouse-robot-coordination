"""The travel-time predictor as a small HTTP service, with fault injection (SPEC.md § optional systems
extension). Simulated systems behaviour, not real robot offloading.

    python -m predictor.serve --model results/models/mlp.json --port 18080 [--latency-ms 250] [--drop-rate 0.2]

POST /predict {"rows": [feature dict, ...]} -> {"pred": [float, ...]}. --latency-ms delays every
reply; --drop-rate closes that share of connections without replying, decided by a seeded RNG in
request order, so a sequential client sees the same drops every run. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from predictor.model import TravelTimeModel


def make_handler(model: TravelTimeModel, latency_s: float, drop_rate: float, seed: int):
    rng, lock = random.Random(seed), threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - http.server naming
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            with lock:
                drop = rng.random() < drop_rate
            if drop:
                self.close_connection = True   # no reply at all: the client sees a dropped connection
                return
            if latency_s:
                time.sleep(latency_s)
            pred = model.predict(json.loads(body)["rows"]).tolist()
            out = json.dumps({"pred": pred}).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)
            except (BrokenPipeError, ConnectionResetError):
                pass   # the client's budget ran out before the (delayed) reply: expected under --latency-ms

        def log_message(self, *args):   # quiet: one line per request would flood the run log
            pass

    return Handler


def serve(model_path: Path, port: int, latency_ms: float = 0.0, drop_rate: float = 0.0, seed: int = 0) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port),
                                 make_handler(TravelTimeModel.load(model_path), latency_ms / 1000, drop_rate, seed))
    server.daemon_threads = True
    return server


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", type=Path, default=Path("results/models/mlp.json"))
    p.add_argument("--port", type=int, default=18080)
    p.add_argument("--latency-ms", type=float, default=0.0)
    p.add_argument("--drop-rate", type=float, default=0.0)
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    serve(a.model, a.port, a.latency_ms, a.drop_rate, a.seed).serve_forever()


if __name__ == "__main__":
    main()
