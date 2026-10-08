# D-GATE Evaluation package

Status: local anonymous-review candidate, not uploaded. This is the Evaluation subtree of the combined top-level package. Read `../README.md` and `../RUN_GUIDE.md` from the package root.

The package includes matching later task code, configurations, saved results/checkpoints, the table-level task data, full current 1 s exports, and the separate T1 predictor inputs required to rebuild the previously omitted tensor cache. `docs/ASSEMBLY_REPORT.md` maps paper figures/tables to these materials; `docs/VERIFICATION.md` records actual replay results and limits.

`evaluation/verification/results/new_training/RETRAINING_VERIFICATION.json` records four separately named local training-flow checks. These new post-paper runs do not replace the historical result files; complete logs and new checkpoints remain outside the release package.

No reviewer URL is embedded. The current field dictionary and 1 s exports have not been established as the exact historical versions behind the manuscript. Historical execution identity remains unconfirmed even where saved outputs and inference match exactly.
