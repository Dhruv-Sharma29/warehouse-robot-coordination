"""Travel-time predictors: realised travel steps for a trip, from decision-time features.

  ridge  linear model on standardised features (a strong, transparent baseline)
  mlp    2x64 MLP trained in PyTorch; predicts log(1 + steps)

Both expose `predict(list[dict]) -> np.ndarray` in numpy only: the MLP's weights are copied out
after training, so the simulator calls no PyTorch per decision (it's called thousands of times
per run, and small-batch PyTorch calls would dominate run time).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from predictor.features import FEATURES


def matrix(rows: list[dict]) -> np.ndarray:
    return np.array([[float(r[f]) for f in FEATURES] for r in rows], dtype=np.float64)


class TravelTimeModel:
    def __init__(self, kind: str, mean: np.ndarray, std: np.ndarray, layers: list[tuple[np.ndarray, np.ndarray]]):
        self.kind, self.mean, self.std, self.layers = kind, mean, std, layers

    def predict(self, rows: list[dict]) -> np.ndarray:
        x = (matrix(rows) - self.mean) / self.std
        for i, (w, b) in enumerate(self.layers):
            x = x @ w + b
            if i < len(self.layers) - 1:
                x = np.maximum(x, 0.0)
        y = x[:, 0]
        return np.expm1(y) if self.kind == "mlp" else y

    def save(self, path: Path) -> None:
        path.write_text(json.dumps({"kind": self.kind, "features": FEATURES, "mean": self.mean.tolist(),
                                    "std": self.std.tolist(), "layers": [[w.tolist(), b.tolist()] for w, b in self.layers]}))

    @classmethod
    def load(cls, path: Path) -> "TravelTimeModel":
        d = json.loads(Path(path).read_text())
        if d["features"] != FEATURES:
            raise ValueError("model was trained on a different feature list")
        return cls(d["kind"], np.array(d["mean"]), np.array(d["std"]),
                   [(np.array(w), np.array(b)) for w, b in d["layers"]])


def fit_ridge(rows: list[dict], y: np.ndarray, alpha: float = 1.0) -> TravelTimeModel:
    X = matrix(rows)
    mean, std = X.mean(0), X.std(0) + 1e-9
    Z = np.hstack([(X - mean) / std, np.ones((len(X), 1))])
    reg = alpha * np.eye(Z.shape[1])
    reg[-1, -1] = 0.0
    coef = np.linalg.solve(Z.T @ Z + reg, Z.T @ y)
    return TravelTimeModel("ridge", mean, std, [(coef[:-1, None], coef[-1:])])


def fit_mlp(rows: list[dict], y: np.ndarray, val_rows: list[dict], val_y: np.ndarray, seed: int = 0,
            epochs: int = 60, hidden: int = 64, lr: float = 2e-3) -> tuple[TravelTimeModel, dict]:
    import torch
    torch.manual_seed(seed)
    torch.set_num_threads(4)
    X = matrix(rows)
    mean, std = X.mean(0), X.std(0) + 1e-9
    xt = torch.tensor((X - mean) / std, dtype=torch.float32)
    yt = torch.tensor(np.log1p(y), dtype=torch.float32)[:, None]
    xv = torch.tensor((matrix(val_rows) - mean) / std, dtype=torch.float32)
    yv = torch.tensor(np.log1p(val_y), dtype=torch.float32)[:, None]
    net = torch.nn.Sequential(torch.nn.Linear(X.shape[1], hidden), torch.nn.ReLU(),
                              torch.nn.Linear(hidden, hidden), torch.nn.ReLU(), torch.nn.Linear(hidden, 1))
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    best, best_state, history = float("inf"), None, []
    g = torch.Generator().manual_seed(seed)
    for epoch in range(epochs):
        net.train()
        for idx in torch.randperm(len(xt), generator=g).split(256):
            opt.zero_grad()
            loss = torch.nn.functional.mse_loss(net(xt[idx]), yt[idx])
            loss.backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            v = torch.nn.functional.mse_loss(net(xv), yv).item()
        history.append(v)
        if v < best:  # early stopping on the validation split (in-distribution layouts, unseen seeds)
            best, best_state = v, {k: t.clone() for k, t in net.state_dict().items()}
    net.load_state_dict(best_state)
    layers = [(m.weight.detach().numpy().T.astype(np.float64), m.bias.detach().numpy().astype(np.float64))
              for m in net if isinstance(m, torch.nn.Linear)]
    return TravelTimeModel("mlp", mean, std, layers), {"best_val_mse_log": best, "epochs": epochs,
                                                       "best_epoch": int(np.argmin(history)) + 1}
