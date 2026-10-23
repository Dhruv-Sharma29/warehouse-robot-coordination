# Environment (recorded 2026-10-06)

| Item | Value |
| --- | --- |
| Host | GB10, aarch64, Ubuntu 24.04.1, 20 CPU cores |
| Python | 3.12.3 (venv created with `--system-site-packages`) |
| numpy / scipy / scikit-learn | 1.26.4 / 1.12.0 / 1.5.2 (system) |
| torch | 2.7.0a0+ecf3bae40a.nv25.02 (NVIDIA build, system) |

The simulator and planners run on CPU. The predictor is small and is trained on CPU too: the GPU
was shared with other long-running jobs at the time, and a model this size gains nothing from it.
