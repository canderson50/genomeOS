2026-10-11 drafted #276 PR canderson50/genomeOS#3 (one-off at canderson50's request, outside the routine): bit-exact H2D helper + CPU/GPU regressions; advances, does not close. A40 pod 02xcywzmu3s3pr 84 passed; runner flagged status.json hash race (runner bug, fork-only).
2026-10-11 drafted newsletter sign-up PR canderson50/genomeOS#4 (at canderson50's request; stacked on #431; needs upstream issue first, website spec §13 non-goal). GA tag still enableHistoryEvents=true at 18:20Z.
2026-10-11 drafted Atlas picker wordmark fix PR canderson50/genomeOS#5 (at canderson50's request; separate from #4, whose shard-1 failure it fixes).
2026-10-12 fixed runpod_job.py status.json manifest race on fork main (370a952, at canderson50's request); verified on A40 pod t6d6pmoloe5sc1: results-verified, 13 passed, $0.02.
2026-10-12 profiled count scoring CPU vs CuPy on A40 pod tdrqbh8uf6vj1c (synthetic, at f3357ce): warm speed-up 47-83x at 3 sizes; obs300 and realshape hit 25-min caps on CPU; $0.80.
2026-10-12 synced: fork main already at upstream f3357ce (no merge needed); fork main 370a952.
2026-10-12 closed: draft canderson50/genomeOS#3 (issue #276); submitted upstream as genomeOS/genomeOS#435.
2026-10-12 skipped: no candidates; agent-state/ready.json is empty (mirror 2026-10-12T02:29Z, 0 Ready of 241 issues).
2026-10-13 synced: fork main already at upstream f3357ce (no merge needed); fork main 370a952.
2026-10-13 skipped: no candidates; agent-state/ready.json is empty (mirror 2026-10-12T23:38Z, 0 Ready of 242 issues). No claude/issue-* drafts open.
2026-10-14 synced: merged upstream 059c1cd (incl. #429 GA4, #437, #447-#450) into fork main; fork main e1f67f9.
2026-10-14 skipped: no candidates; agent-state/ready.json is empty (mirror 2026-10-14T10:18Z, 0 Ready of 251 issues). No claude/issue-* drafts open.
2026-10-14 noted: claude/newsletter-signup (#4/upstream #441) and claude/atlas-picker-wordmark (#5/upstream #440) now conflict with upstream main; outside routine scope, reported to canderson50.
2026-10-15 synced: merged upstream 412f86b into fork main; fork main 003c7aa.
2026-10-15 skipped: no candidates; agent-state/ready.json is empty (mirror 2026-10-15T10:02Z, 0 Ready of 254 issues). No claude/issue-* drafts open.
2026-10-15 ran #442 lean stage 0 (at canderson50's request, branch claude/issue-442-sbc-stage0 @26544c6): prior predictive (local CPU, 1000 draws, 672 MAP sites) + pilot on A40 pod 239rrcl0l7nx7k: 9/9 fits converged, 414-997 s each, divergences in 4/9; $0.88.
2026-10-16 synced: merged upstream 1d55838 (#462 site redesign) into fork main; fork main 85adb21.
2026-10-16 skipped: no candidates; agent-state/ready.json is empty (mirror 2026-10-16T09:55Z, 0 Ready of 256 issues). No claude/issue-* drafts open.
2026-10-19 synced: merged upstream e1706b4 (incl. #435 merged, #474 data store, #489 HbS parity input release) into fork main; fork main a9b1245.
2026-10-19 skipped: no candidates; agent-state/ready.json is empty (mirror 2026-10-19T10:54Z, 0 Ready of 268 issues). No claude/issue-* drafts open.
2026-10-19 updated mirror_board.py to copy PR comments, reviews and review threads (at canderson50's request; fork main c808f85); mirror rerun 6777487.
2026-10-19 updated: upstream #402 (issue #258) per bschilder's review, at canderson50's request: PYTHONPATH fix on 3 sibling call sites (53cc572); full pytest 6484 passed, 37 skipped.
2026-10-19 updated: upstream #424 (no issue) at canderson50's request: merged upstream e1706b4 (hf-dataset-card conflict, took #474 text) and fixed CONTRIBUTING pages/#470 line + overview data-store/web-bucket lines (acb57e0); docs tests 476 passed, rebuild 11 rows x2, merge-tree clean.
2026-10-19 updated: upstream #399 (issue #280) per bschilder's review, at canderson50's request: merged upstream e1706b4; antipodal NaN + balanced-anchor fixes, n_inducing guard, tie warning (1f2368d); HbS tie check on release 2026-10-18 parity input: main/PR/update byte-identical, no tie; full pytest 7212 passed, 52 skipped.
2026-10-19 standing instruction from canderson50: never request reviews from dwgoblue (or add them as a reviewer) on any PR. Note: upstream CODEOWNERS (* @bschilder @dwgoblue) auto-requests them on upstream PRs; that is GitHub's doing, not ours.
2026-10-19 ran #45 exploratory overdispersion preflight (CPU, at canderson50's request; branch claude/issue-45-overdispersion-preflight @a90d39a): zero-survey pull 3.6x (beta-binomial k=46) vs 135x (Piel logit noise V=0.45); non-spatial fit favours beta-binomial (-0.15 nats/survey held out, 0/5 folds). Drafted #45 reply with pre-registered comparison 1 (start 26 Oct unless bschilder objects).
2026-10-19 raised RunPod per-pod cap 120 -> 180 min at canderson50's request: runpod_job.py MAX_MINUTES on fork main (205ae10); scheduled task 'genomeOS PR drafter' instructions updated to match (3 hours / --minutes at most 180). Budget, rate cap and one-pod rule unchanged.
2026-10-19 drafted: issue #111 (advances, does not close), canderson50/genomeOS#6, at canderson50's request: build_surfaces.py default draws 400 -> 1200 (0cf7592); full pytest 7199 passed, 52 skipped. Found: artifact manifests omit the sampling budget (not fixed).
2026-10-19 closed: canderson50/genomeOS#6 (issue #111), submitted upstream as #493.
2026-10-19 drafted: issue #39 (advances), canderson50/genomeOS#7, at canderson50's request: mask.contraction_report (d346819); full pytest 7204 passed, 52 skipped.
2026-10-19 drafted: issue #198 (closes), canderson50/genomeOS#8, at canderson50's request: tests/test_surface_fit_replay.py (6648d00); full pytest 7200 passed, 52 skipped; replay tests fail on 33aa2e1 (pre-#203) as #198 recorded.
2026-10-20 closed: canderson50/genomeOS#7 (issue #39), submitted upstream as #494.
2026-10-20 closed: canderson50/genomeOS#8 (issue #198), submitted upstream as #495.
2026-10-20 skipped: no candidates; agent-state/ready.json is empty (mirror 2026-10-20T10:09Z, 0 Ready of 268 issues). No claude/issue-* drafts open.
2026-10-21 skipped: no candidates; agent-state/ready.json is empty (mirror 2026-10-21T10:17Z, 0 Ready of 269 issues). No claude/issue-* drafts open.
2026-10-22 skipped: no candidates; agent-state/ready.json is empty (mirror 2026-10-22T10:18Z, 0 Ready of 269 issues). No claude/issue-* drafts open.
2026-10-23 skipped: no candidates; agent-state/ready.json is empty (mirror 2026-10-23T10:11Z, 0 Ready of 269 issues). No claude/issue-* drafts open.
2026-10-26 skipped: no candidates; agent-state/ready.json is empty (mirror 2026-10-26T11:14Z, 0 Ready of 269 issues). No claude/issue-* drafts open.
2026-10-27 skipped: no candidates; agent-state/ready.json is empty (mirror 2026-10-27T10:40Z, 0 Ready of 269 issues). No claude/issue-* drafts open.
