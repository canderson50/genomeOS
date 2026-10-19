"""Exploratory preflight for #45: does Piel's per-site logit noise keep zero surveys informative?

Design §7 (observation model) and §8 (golden test 1). The 2026-09-16 HbS parity run leaves a
~1% non-endemic floor. #103 traced part of it to the beta-binomial: at the fitted concentration
(~46) a survey with AC=0 of AN=2,000 is ~25% likely at a local frequency of 0.78%, so large zero
surveys barely pull the background down. Piel et al. 2013 (Web Appendix 1, pp. 11-12; Web
Table 5) used a binomial likelihood with an independent normal term on the latent scale instead
(nugget variance V ~ 0.45). This script compares the two observation models without any spatial
fit. It is a preflight, not a decision: it cannot say which surface either model would produce.

Part A (mechanism). At matched local mean frequencies, how likely is a zero survey, and how
strongly does one prefer a near-zero background over the canonical floor, under each model?

Part B (data). Both models fitted non-spatially by maximum likelihood to the 994 parity surveys,
scored on held-out surveys with the project's grouped (whole-cohort) and spatial folds. A
non-spatial fit pushes all geographic variation into the dispersion term, so Part B only asks
which family describes the spread of survey frequencies, zeros included, better.

Inputs are the published parity observations (data release 2026-10-18), checked against their
pinned sha256. Deterministic: grouped folds are seedless and spatial folds use SEED = 42.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq, minimize
from scipy.special import betaln, expit, gammaln, log_expit, logsumexp

from genomeos.validation.crossval import make_folds

PINNED_SHA256 = "466034e22015ce5f4e0b90067adb2232491b625591d50c8ac83d955565345b4b"
#: Beta-binomial concentration of the canonical 2026-09-16 fit (#103) and of #83's comparison.
GENOMEOS_CONCENTRATIONS = (46.0, 36.0)
#: Piel 2013 Web Table 5, nugget variance (mean 0.450), with a sensitivity bracket.
PIEL_NUGGET_VARIANCES = (0.45, 0.2, 1.0)
LOCAL_MEANS = (0.0005, 0.001, 0.005, 0.0078, 0.01, 0.02)
ZERO_SURVEY_SIZES = (234, 2000, 5000)
CANONICAL_FLOOR = 0.0078
NEAR_ZERO = 0.0005
NODES = 40


def _log_choose(n: np.ndarray, k: np.ndarray) -> np.ndarray:
    return gammaln(n + 1) - gammaln(k + 1) - gammaln(n - k + 1)


def beta_binomial_logpmf(k, n, mean: float, concentration: float) -> np.ndarray:
    k, n = np.asarray(k, dtype=float), np.asarray(n, dtype=float)
    a, b = mean * concentration, (1.0 - mean) * concentration
    return _log_choose(n, k) + betaln(k + a, n - k + b) - betaln(a, b)


def logit_normal_binomial_logpmf(k, n, location: float, variance: float, nodes: int = NODES):
    """log P(k | n) for k ~ Binomial(n, expit(z)), z ~ Normal(location, variance).

    Adaptive Gauss-Hermite: each survey's integrand is centred on its own mode and scaled by its
    curvature, so a 2.5-million-allele survey is integrated as accurately as a 50-allele one.
    """
    k, n = np.asarray(k, dtype=float), np.asarray(n, dtype=float)
    # The log-integrand is strictly concave, so its gradient falls monotonically and the mode is
    # its unique root. Bisection, not Newton: undamped Newton overshoots and oscillates on it
    # (it did, for a 43-of-196 survey, and silently centred the quadrature in the wrong place).
    low = np.full(k.shape, -60.0)
    high = np.full(k.shape, 60.0)
    for _ in range(120):
        z = 0.5 * (low + high)
        rising = k - n * expit(z) - (z - location) / variance > 0
        low = np.where(rising, z, low)
        high = np.where(rising, high, z)
    z = 0.5 * (low + high)
    scale = 1.0 / np.sqrt(n * expit(z) * (1.0 - expit(z)) + 1.0 / variance)
    x, w = np.polynomial.hermite.hermgauss(nodes)
    points = z[:, None] + np.sqrt(2.0) * scale[:, None] * x[None, :]
    log_integrand = (
        k[:, None] * log_expit(points)
        + (n - k)[:, None] * log_expit(-points)
        - (points - location) ** 2 / (2.0 * variance)
    )
    log_integral = logsumexp(log_integrand + x[None, :] ** 2 + np.log(w)[None, :], axis=1)
    log_integral += np.log(np.sqrt(2.0) * scale) - 0.5 * np.log(2.0 * np.pi * variance)
    return _log_choose(n, k) + log_integral


def logit_location_for_mean(mean: float, variance: float) -> float:
    """The latent location whose logit-normal frequency has the given mean."""
    x, w = np.polynomial.hermite.hermgauss(80)

    def gap(location: float) -> float:
        return float(np.sum(w * expit(location + np.sqrt(2.0 * variance) * x)) / np.sqrt(np.pi)) - mean

    return brentq(gap, -40.0, 10.0, xtol=1e-12)


def part_a() -> dict:
    """Zero-survey probability and pull, at matched local means."""
    rows = []
    for size in ZERO_SURVEY_SIZES:
        for mean in LOCAL_MEANS:
            row = {"an": size, "local_mean": mean, "binomial": float((1.0 - mean) ** size)}
            for kappa in GENOMEOS_CONCENTRATIONS:
                row[f"beta_binomial_k{kappa:g}"] = float(
                    np.exp(beta_binomial_logpmf([0], [size], mean, kappa))[0]
                )
            for v in PIEL_NUGGET_VARIANCES:
                location = logit_location_for_mean(mean, v)
                row[f"logit_normal_v{v:g}"] = float(
                    np.exp(logit_normal_binomial_logpmf([0], [size], location, v))[0]
                )
            rows.append(row)
    table = pd.DataFrame(rows)
    pull = {}
    for column in [c for c in table.columns if c not in ("an", "local_mean")]:
        for size in ZERO_SURVEY_SIZES:
            at = table[table.an == size].set_index("local_mean")[column]
            pull[f"{column}@an{size}"] = float(np.log10(at[NEAR_ZERO] / at[CANONICAL_FLOOR]))
    return {"zero_probability": rows, "log10_likelihood_ratio_near_zero_vs_floor": pull}


def fit_beta_binomial(k, n) -> tuple[float, float, float]:
    def nll(theta):
        return -beta_binomial_logpmf(k, n, expit(theta[0]), np.exp(theta[1])).sum()

    best = minimize(
        nll,
        x0=[-3.0, np.log(20.0)],
        method="Nelder-Mead",
        options={"xatol": 1e-9, "fatol": 1e-9, "maxiter": 20000},
    )
    return float(expit(best.x[0])), float(np.exp(best.x[1])), float(-best.fun)


def fit_logit_normal(k, n) -> tuple[float, float, float]:
    def nll(theta):
        return -logit_normal_binomial_logpmf(k, n, theta[0], np.exp(theta[1])).sum()

    best = minimize(
        nll, x0=[-3.0, 0.0], method="Nelder-Mead", options={"xatol": 1e-9, "fatol": 1e-9, "maxiter": 20000}
    )
    return float(best.x[0]), float(np.exp(best.x[1])), float(-best.fun)


def part_b(observations: pd.DataFrame) -> dict:
    k, n = observations["ac"].to_numpy(float), observations["an"].to_numpy(float)
    result: dict = {}
    bb_mean, bb_kappa, bb_ll = fit_beta_binomial(k, n)
    ln_loc, ln_var, ln_ll = fit_logit_normal(k, n)
    result["full_data"] = {
        "beta_binomial": {"mean": bb_mean, "concentration": bb_kappa, "log_likelihood": bb_ll},
        "logit_normal": {"location": ln_loc, "variance": ln_var, "log_likelihood": ln_ll},
        "log_likelihood_difference": ln_ll - bb_ll,
        "parameters_each": 2,
    }
    for strategy in ("grouped", "spatial"):
        folds = make_folds(observations, n_folds=5, strategy=strategy)
        diff = np.empty(len(observations))
        per_fold = []
        for fold in range(5):
            train, test = folds != fold, folds == fold
            m, c, _ = fit_beta_binomial(k[train], n[train])
            loc, var, _ = fit_logit_normal(k[train], n[train])
            bb = beta_binomial_logpmf(k[test], n[test], m, c)
            ln = logit_normal_binomial_logpmf(k[test], n[test], loc, var)
            diff[test] = ln - bb
            per_fold.append(float(np.mean(ln - bb)))
        cohort_macro = pd.Series(diff).groupby(observations["cohort_id"].to_numpy()).mean().mean()
        zero = k == 0
        result[strategy] = {
            "logit_normal_minus_beta_binomial_nats_per_survey": {
                "cohort_macro_mean": float(cohort_macro),
                "row_mean": float(diff.mean()),
                "zero_surveys": float(diff[zero].mean()),
                "positive_surveys": float(diff[~zero].mean()),
                "per_fold_row_mean": per_fold,
                "folds_improved": int(sum(d > 0 for d in per_fold)),
            }
        }
    return result


def self_checks() -> dict:
    """Agreement with a reference implementation, the zero-variance limit, quadrature stability.

    The beta-binomial is checked against scipy's own, not against a large-concentration binomial
    limit: for a 2.5-million-allele survey no representable concentration is "large", and the
    log-beta terms lose precision long before it would be.
    """
    from scipy.stats import betabinom

    k = np.array([0, 3, 44431, 0])
    n = np.array([2000, 50, 2571112, 5000])
    binom = _log_choose(n, k) + k * np.log(0.01) + (n - k) * np.log(0.99)
    bb_ours = beta_binomial_logpmf(k, n, 0.01, 46.0)
    bb_scipy = betabinom.logpmf(k, n, 0.01 * 46.0, 0.99 * 46.0)
    ln_limit = logit_normal_binomial_logpmf(k, n, np.log(0.01 / 0.99), 1e-16)
    coarse = logit_normal_binomial_logpmf(k, n, -4.0, 0.45, nodes=NODES)
    fine = logit_normal_binomial_logpmf(k, n, -4.0, 0.45, nodes=2 * NODES)
    # Brute force on a dense grid, for surveys of ordinary size, at a wide and a narrow variance.
    # This is what catches a quadrature centred in the wrong place, which the node-doubling
    # check above cannot: both node counts would be centred on the same wrong point.
    grid_errors = []
    small_k, small_n = np.array([43, 0, 3, 120, 0]), np.array([196, 2000, 50, 400, 234])
    for location, variance in ((-3.28, 3.72), (-4.0, 0.45)):
        z = np.linspace(location - 14 * np.sqrt(variance), location + 14 * np.sqrt(variance), 400001)
        log_prior = -((z - location) ** 2) / (2 * variance) - 0.5 * np.log(2 * np.pi * variance)
        for kk, nn in zip(small_k, small_n, strict=True):
            integrand = kk * log_expit(z) + (nn - kk) * log_expit(-z) + log_prior
            brute = _log_choose(nn, kk) + logsumexp(integrand) + np.log(z[1] - z[0])
            ours = logit_normal_binomial_logpmf([kk], [nn], location, variance)[0]
            grid_errors.append(abs(float(ours - brute)))
    return {
        "logit_normal_vs_brute_force_grid_max_abs_log_diff": max(grid_errors),
        "beta_binomial_vs_scipy_max_abs_log_diff": float(np.abs(bb_ours - bb_scipy).max()),
        "logit_normal_to_binomial_max_abs_log_diff": float(np.abs(ln_limit - binom).max()),
        "quadrature_40_vs_80_nodes_max_abs_log_diff": float(np.abs(coarse - fine).max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    digest = hashlib.sha256(args.observations.read_bytes()).hexdigest()
    if digest != PINNED_SHA256:
        raise SystemExit(f"refusing {args.observations}: sha256 {digest} is not the pinned parity input")
    observations = pd.read_parquet(args.observations)
    report = {
        "status": "exploratory preflight; no spatial fit; decides nothing",
        "input_sha256": digest,
        "surveys": len(observations),
        "zero_surveys": int((observations["ac"] == 0).sum()),
        "cohorts": int(observations["cohort_id"].nunique()),
        "self_checks": self_checks(),
        "part_a": part_a(),
        "part_b": part_b(observations),
    }
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("surveys", "zero_surveys", "cohorts", "self_checks")}, indent=2))


if __name__ == "__main__":
    main()
