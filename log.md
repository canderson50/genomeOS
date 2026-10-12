2026-10-11 drafted #276 PR canderson50/genomeOS#3 (one-off at canderson50's request, outside the routine): bit-exact H2D helper + CPU/GPU regressions; advances, does not close. A40 pod 02xcywzmu3s3pr 84 passed; runner flagged status.json hash race (runner bug, fork-only).
2026-10-11 drafted newsletter sign-up PR canderson50/genomeOS#4 (at canderson50's request; stacked on #431; needs upstream issue first, website spec §13 non-goal). GA tag still enableHistoryEvents=true at 18:20Z.
2026-10-11 drafted Atlas picker wordmark fix PR canderson50/genomeOS#5 (at canderson50's request; separate from #4, whose shard-1 failure it fixes).
2026-10-12 fixed runpod_job.py status.json manifest race on fork main (370a952, at canderson50's request); verified on A40 pod t6d6pmoloe5sc1: results-verified, 13 passed, $0.02.
2026-10-12 profiled count scoring CPU vs CuPy on A40 pod tdrqbh8uf6vj1c (synthetic, at f3357ce): warm speed-up 47-83x at 3 sizes; obs300 and realshape hit 25-min caps on CPU; $0.80.
