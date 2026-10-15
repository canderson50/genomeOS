#!/usr/bin/env python3
"""Stage 0 for simulation-based calibration of the surface model (design §§7-8, 12; #442).

Two bounded probes that inform the #442 pre-registration and claim nothing about calibration:

- ``prior``: a prior predictive check. Draws the published HbS configuration's priors
  (inducing-point GP, 150 H3 inducing cells, beta-binomial, study cohorts) on the public MAP
  survey geometry and summarises the implied allele frequencies at the sites and across the globe.
- ``pilot``: a timing and convergence pilot. Simulates a few datasets from those priors on the same
  geometry and fits each with the unchanged ``fit_surface``, recording wall time, sampler
  diagnostics and the rank of each true scalar among thinned posterior draws.

Geometry only comes from the MAP export: coordinates, typed sample sizes and the citing study.
No observed allele count is used, so the raw export's missing sampling-radius evidence does not
matter here, and every output is synthetic, nonpublication research evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

from genomeos.surfaces.config import JITTER, FitConfig  # noqa: E402
from genomeos.surfaces.convergence import summarize_sampler_diagnostics  # noqa: E402
from genomeos.surfaces.fit import (  # noqa: E402
    ConvergenceError,
    derive_lengthscale_prior,
    fit_surface,
    h3_inducing_points,
    to_unit_sphere,
)

SEED = 42
VARIANT = "chr11-5227002-T-A"
SCALARS = ("lengthscale", "amplitude", "intercept", "cohort_sd", "concentration")
RANK_DRAWS = 100
FAR_KM = 2000.0


def published_config(draws: int, tune: int) -> FitConfig:
    """The configuration `build_surfaces.py` publishes HbS with, at a stated sampling budget."""
    return FitConfig(
        approximation="inducing",
        inducing_placement="h3",
        n_inducing=150,
        draws=draws,
        tune=tune,
        chains=4,
    )


def load_geometry(path: Path) -> pd.DataFrame:
    """Sites with complete typed genotypes: coordinates, allele number and citing study."""
    raw = pd.read_csv(path)
    genotypes = raw[["hbaa", "hbas", "hbss"]].apply(pd.to_numeric, errors="coerce")
    typed = genotypes.sum(axis=1, min_count=3)
    keep = (
        genotypes.notna().all(axis=1)
        & (typed > 0)
        & raw["latitude"].between(-90, 90)
        & raw["longitude"].between(-180, 180)
        & raw["citation"].notna()
    )
    sites = pd.DataFrame(
        {
            "site": raw.loc[keep, "id"].astype(str),
            "lat": raw.loc[keep, "latitude"].astype(float),
            "lon": raw.loc[keep, "longitude"].astype(float),
            "an": (2 * typed[keep]).astype(int),
            "cohort": raw.loc[keep, "citation"].astype(str),
            "observed_af": ((genotypes["hbas"] + 2 * genotypes["hbss"]) / (2 * typed))[keep],
        }
    ).reset_index(drop=True)
    if sites.empty:
        raise ValueError("no MAP rows with complete typed genotypes")
    return sites


def matern52(a: np.ndarray, b: np.ndarray, amplitude: float, lengthscale: float) -> np.ndarray:
    """PyMC's Matern52 on unit-sphere coordinates (chordal distance)."""
    r = np.sqrt(np.maximum(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1), 0.0)) / lengthscale
    return amplitude**2 * (1.0 + np.sqrt(5.0) * r + 5.0 / 3.0 * r**2) * np.exp(-np.sqrt(5.0) * r)


def fibonacci_sphere(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Near-uniform global query points as (lat, lon) in degrees."""
    k = np.arange(n) + 0.5
    lat = np.degrees(np.arcsin(1.0 - 2.0 * k / n))
    lon = (np.degrees(np.pi * (1.0 + 5.0**0.5) * k) + 180.0) % 360.0 - 180.0
    return lat, lon


def nearest_km(lat: np.ndarray, lon: np.ndarray, site_lat: np.ndarray, site_lon: np.ndarray):
    """Great-circle distance from each query point to its nearest site."""
    a = to_unit_sphere(lat, lon)
    b = to_unit_sphere(site_lat, site_lon)
    cos = np.clip(a @ b.T, -1.0, 1.0)
    return 6371.0088 * np.arccos(cos.max(axis=1))


class PriorModel:
    """The published configuration's prior, evaluated with the same inducing construction."""

    def __init__(self, sites: pd.DataFrame, config: FitConfig, queries: tuple | None = None):
        self.sites = sites
        lat, lon = sites["lat"].to_numpy(), sites["lon"].to_numpy()
        self.ls_mu, self.ls_sigma, self.anchor_low, self.anchor_high = derive_lengthscale_prior(lat, lon)
        self.inducing = h3_inducing_points(lat, lon, config.n_inducing, config.inducing_reach_km)
        self.x_sites = to_unit_sphere(lat, lon)
        self.x_query = None if queries is None else to_unit_sphere(*queries)
        codes, self.cohorts = pd.factorize(sites["cohort"])
        self.cohort_index = codes

    def draw(self, rng: np.random.Generator) -> dict:
        truth = {
            "lengthscale": float(rng.lognormal(self.ls_mu, self.ls_sigma)),
            "amplitude": float(abs(rng.normal(0.0, 1.0))),
            "intercept": float(rng.normal(-3.5, 1.5)),
            "cohort_sd": float(abs(rng.normal(0.0, 0.5))),
            "concentration": float(abs(rng.normal(0.0, 100.0))),
        }
        k_uu = matern52(self.inducing, self.inducing, truth["amplitude"], truth["lengthscale"])
        chol = np.linalg.cholesky(k_uu + JITTER * np.eye(len(self.inducing)))
        weights = np.linalg.solve(chol.T, rng.standard_normal(len(self.inducing)))

        def field(x):
            k = matern52(x, self.inducing, truth["amplitude"], truth["lengthscale"])
            return truth["intercept"] + k @ weights

        cohort_effect = truth["cohort_sd"] * rng.standard_normal(len(self.cohorts))
        logit = field(self.x_sites) + cohort_effect[self.cohort_index]
        p = 1.0 / (1.0 + np.exp(-logit))
        conc = max(truth["concentration"], 1e-6)
        q = rng.beta(np.maximum(p * conc, 1e-12), np.maximum((1.0 - p) * conc, 1e-12))
        ac = rng.binomial(self.sites["an"].to_numpy(), q)
        query_p = None
        if self.x_query is not None:
            query_p = 1.0 / (1.0 + np.exp(-field(self.x_query)))
        return {"truth": truth, "ac": ac, "site_p": p, "query_p": query_p}

    def observations(self, ac: np.ndarray) -> pd.DataFrame:
        s = self.sites
        return pd.DataFrame(
            {
                "variant_id": VARIANT,
                "rsid": "rs334",
                "population_id": "map-site-" + s["site"],
                "lat": s["lat"],
                "lon": s["lon"],
                "radius_km": 25.0,
                "ac": ac.astype("int64"),
                "an": s["an"].astype("int64"),
                "source_record_id": "sbc-stage0:" + s["site"],
                "source": "synthetic-sbc-stage0",
                "assay": "genotype",
                "date_lower": 0,
                "date_upper": 0,
                "sampling_design": "population_random",
                "disease_ascertainment_excluded": False,
                "cohort_id": "study-" + pd.Series(self.cohort_index).astype(str),
                "ingest_version": "sbc-stage0",
            }
        )


def quantiles(values: np.ndarray) -> dict:
    qs = (0.05, 0.25, 0.5, 0.75, 0.95, 0.99)
    return {f"q{int(q * 100):02d}": float(np.quantile(values, q)) for q in qs}


def run_prior(args) -> dict:
    sites = load_geometry(args.geometry)
    queries = fibonacci_sphere(args.query_points)
    model = PriorModel(sites, published_config(400, 400), queries)
    far = nearest_km(*queries, sites["lat"].to_numpy(), sites["lon"].to_numpy()) > FAR_KM
    rng = np.random.default_rng(SEED)
    site_af, query_p, far_p, world = [], [], [], []
    for _ in range(args.draws):
        sim = model.draw(rng)
        site_af.append(sim["ac"] / sites["an"].to_numpy())
        query_p.append(sim["query_p"])
        far_p.append(sim["query_p"][far])
        world.append({t: float((sim["query_p"] > t).mean()) for t in (0.01, 0.05, 0.2, 0.5)})
    site_af, query_p, far_p = map(np.concatenate, (site_af, query_p, far_p))
    observed = sites["observed_af"].to_numpy()
    return {
        "probe": "prior_predictive",
        "evidence_kind": "synthetic_prior_predictive",
        "publication_eligible": False,
        "geometry": {
            "sites": len(sites),
            "cohorts": int(len(model.cohorts)),
            "an_median": int(sites["an"].median()),
            "inducing_points": len(model.inducing),
            "lengthscale_anchor_km": [model.anchor_low, model.anchor_high],
        },
        "draws": args.draws,
        "observed_site_af": {**quantiles(observed), "zero_fraction": float((observed == 0).mean())},
        "prior_site_af": {**quantiles(site_af), "zero_fraction": float((site_af == 0).mean())},
        "prior_global_frequency": quantiles(query_p),
        "prior_far_from_sites_frequency": {
            "far_km": FAR_KM,
            "far_fraction_of_globe": float(far.mean()),
            **quantiles(far_p),
        },
        "prior_world_share_above": {
            str(t): quantiles(np.array([w[t] for w in world])) for t in (0.01, 0.05, 0.2, 0.5)
        },
    }


def rank_of_truth(posterior: np.ndarray, truth: float) -> int:
    flat = posterior.reshape(-1)
    thinned = flat[np.linspace(0, flat.size - 1, RANK_DRAWS).astype(int)]
    return int((thinned < truth).sum())


def run_pilot(args) -> None:
    import jax

    sites = load_geometry(args.geometry)
    config = published_config(args.draws, args.tune)
    model = PriorModel(sites, config)
    out = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "probe": "timing_convergence_pilot",
        "evidence_kind": "synthetic_sbc_pilot",
        "publication_eligible": False,
        "config": asdict(config),
        "sites": len(sites),
        "cohorts": int(len(model.cohorts)),
        "geometry_sha256": hashlib.sha256(args.geometry.read_bytes()).hexdigest(),
        "jax_devices": [str(d) for d in jax.devices()],
        "python": platform.python_version(),
    }
    with out.open("w") as handle:
        handle.write(json.dumps(header) + "\n")
    started = time.time()
    for index in range(args.fits):
        if (time.time() - started) / 60 > args.budget_minutes:
            break
        rng = np.random.default_rng([SEED, index])
        sim = model.draw(rng)
        record = {"fit": index, "truth": sim["truth"]}
        t0 = time.time()
        try:
            fit = fit_surface(model.observations(sim["ac"]), config)
            idata = fit.idata
            record["status"] = "converged"
            record["diagnostics"] = asdict(
                summarize_sampler_diagnostics(idata, chains=config.chains, draws=config.draws)
            )
            record["ranks_of_100"] = {
                name: rank_of_truth(idata.posterior[name].values, sim["truth"][name])
                for name in SCALARS
                if name in idata.posterior
            }
        except ConvergenceError as error:
            record["status"] = "not_converged"
            record["reason"] = str(error)
            if error.diagnostics is not None:
                record["diagnostics"] = asdict(error.diagnostics)
        except Exception as error:  # a refusal or failure is a result, never dropped (§12)
            record["status"] = "error"
            record["reason"] = f"{type(error).__name__}: {error}"[:500]
        record["seconds"] = round(time.time() - t0, 1)
        with out.open("a") as handle:
            handle.write(json.dumps(record) + "\n")
        print(json.dumps({k: record[k] for k in ("fit", "status", "seconds")}), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("probe", choices=("prior", "pilot"))
    parser.add_argument("--geometry", type=Path, required=True, help="raw MAP HbS export CSV")
    parser.add_argument("--draws", type=int, default=1000)
    parser.add_argument("--tune", type=int, default=1200)
    parser.add_argument("--query-points", type=int, default=2000)
    parser.add_argument("--fits", type=int, default=12)
    parser.add_argument("--budget-minutes", type=float, default=95.0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.probe == "prior":
        report = run_prior(args)
        text = json.dumps(report, indent=2)
        if args.out:
            args.out.write_text(text + "\n")
        print(text)
    else:
        if args.out is None:
            parser.error("pilot needs --out")
        run_pilot(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
