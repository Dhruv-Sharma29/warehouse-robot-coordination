# Superseded: results with the first router ("clear" mode)

Data, models and comparisons produced while WHCA* used "clear" rounds (drop all reservations;
unplanned robots treated as obstacles for 2 steps). That router needed ~400–2000 safety-layer
interventions per run. Rolling rounds (`planners/whca.py`) removed them and raised baseline
throughput 24% on training layouts (`results/summary/router_ablation.json`). The data was
re-collected, the models retrained, the heuristic re-tuned and the comparison re-run on the
improved router. Kept as evidence, not reported.
