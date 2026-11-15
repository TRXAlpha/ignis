"""Physics-form Bayesian flammability boundary (numpy only).

Latent burn propensity f(a, X) = (X - B(a)) / s, P(burns) = sigmoid(f), with the boundary
    B(a) = D + A exp(-k a) + c a        (X = O2 vol%, a = stretch rate 1/s)
i.e. a quenching branch (radiative loss dominates at low stretch, exponential) plus a blowoff branch
(finite-rate kinetics at high stretch, linear). That functional form is the one BASS-II used (NASA/TM-20210011385
Eq. 6.1, PDF p83); its parameters are NOT taken from the paper, they are fitted here from the observations
with weak priors, and their uncertainty is propagated by a Laplace approximation of the posterior.

Why not a free-form GP: ~50 binary points along one boundary. A GP classifier would interpolate fine but
extrapolate to nonsense (e.g. predicting a minimum O2 outside the data). The physics form constrains the shape;
the posterior band says how sure we are. Validation (model/validate.py) checks it against a 1g-derived baseline.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PARAMS = ("log_A", "log_k", "c", "D", "log_s")
# Weak priors (mean, sd) on unconstrained params. Wide on purpose: the data must decide.
PRIOR_MEAN = np.array([np.log(3.0), np.log(1.0), 0.0, 15.0, np.log(0.5)])
PRIOR_SD = np.array([1.5, 1.5, 0.05, 5.0, 1.0])


def boundary(a: np.ndarray, th: np.ndarray) -> np.ndarray:
    A, k, c, D = np.exp(th[..., 0:1]), np.exp(th[..., 1:2]), th[..., 2:3], th[..., 3:4]
    return D + A * np.exp(-k * a) + c * a


def latent(a: np.ndarray, x: np.ndarray, th: np.ndarray) -> np.ndarray:
    return (x - boundary(a, th)) / np.exp(th[..., 4:5])


def _log_sigmoid(z):
    return -np.logaddexp(0.0, -z)


def neg_log_post(th: np.ndarray, a: np.ndarray, x: np.ndarray, y: np.ndarray) -> float:
    f = latent(a, x, th[None, :])[0]
    ll = np.sum(y * _log_sigmoid(f) + (1 - y) * _log_sigmoid(-f))
    lp = -0.5 * np.sum(((th - PRIOR_MEAN) / PRIOR_SD) ** 2)
    return float(-(ll + lp))


def _grad_hess(fun, th, h=1e-4):
    n = len(th)
    g, H = np.zeros(n), np.zeros((n, n))
    f0 = fun(th)
    E = np.eye(n) * h
    for i in range(n):
        fp, fm = fun(th + E[i]), fun(th - E[i])
        g[i] = (fp - fm) / (2 * h)
        H[i, i] = (fp - 2 * f0 + fm) / h ** 2
        for j in range(i + 1, n):
            H[i, j] = H[j, i] = (fun(th + E[i] + E[j]) - fun(th + E[i] - E[j]) - fun(th - E[i] + E[j])
                                 + fun(th - E[i] - E[j])) / (4 * h * h)
    return g, H


@dataclass
class Fit:
    theta: np.ndarray
    cov: np.ndarray
    n: int
    converged: bool

    def samples(self, n: int = 2000, seed: int = 0) -> np.ndarray:
        rng = np.random.default_rng(seed)
        return rng.multivariate_normal(self.theta, self.cov, size=n)


def fit(a, x, y, starts: int = 12, seed: int = 0) -> Fit:
    """MAP by damped Newton from several prior draws, then Laplace covariance = inverse Hessian."""
    a, x, y = map(lambda v: np.asarray(v, float), (a, x, y))
    if len(a) == 0:
        raise ValueError("no observations to fit")
    fun = lambda th: neg_log_post(th, a, x, y)  # noqa: E731
    rng = np.random.default_rng(seed)
    best, best_v = None, np.inf
    inits = [PRIOR_MEAN] + [PRIOR_MEAN + PRIOR_SD * rng.standard_normal(5) * 0.5 for _ in range(starts - 1)]
    for th in inits:
        th = th.copy()
        lam = 1e-2
        v = fun(th)
        for _ in range(200):
            g, H = _grad_hess(fun, th)
            try:
                step = np.linalg.solve(H + lam * np.eye(5), g)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            cand = th - step
            cv = fun(cand)
            if np.isfinite(cv) and cv < v:
                th, v, lam = cand, cv, max(lam / 3, 1e-6)
                if np.max(np.abs(step)) < 1e-7:
                    break
            else:
                lam *= 10
                if lam > 1e8:
                    break
        if v < best_v:
            best, best_v = th, v
    _, H = _grad_hess(fun, best)
    w, V = np.linalg.eigh(H)
    converged = bool(np.all(w > 0))
    cov = V @ np.diag(1.0 / np.clip(w, 1e-6, None)) @ V.T
    return Fit(theta=best, cov=cov, n=len(a), converged=converged)


def predict(fit_: Fit, a, x, n_samples: int = 2000) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Posterior predictive P(burns): mean, sd over parameter uncertainty, and per-sample probabilities."""
    S = fit_.samples(n_samples)
    a, x = np.asarray(a, float).ravel(), np.asarray(x, float).ravel()
    p = 1.0 / (1.0 + np.exp(-latent(a[None, :], x[None, :], S)))
    return p.mean(0), p.std(0), p


def boundary_band(fit_: Fit, a, n_samples: int = 2000, q=(5, 50, 95)) -> dict:
    S = fit_.samples(n_samples)
    B = boundary(np.asarray(a, float)[None, :], S)
    return {f"p{qq:02d}": np.percentile(B, qq, axis=0) for qq in q}


def min_o2(fit_: Fit, a_grid, n_samples: int = 2000) -> dict:
    S = fit_.samples(n_samples)
    B = boundary(np.asarray(a_grid, float)[None, :], S)
    mins, at = B.min(1), np.asarray(a_grid)[B.argmin(1)]
    return {"p05": float(np.percentile(mins, 5)), "p50": float(np.median(mins)), "p95": float(np.percentile(mins, 95)),
            "at_x": float(np.median(at))}


def entropy(p):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return -(p * np.log(p) + (1 - p) * np.log(1 - p))


def mutual_information(p_samples: np.ndarray) -> np.ndarray:
    """BALD: expected information gain (nats) about the parameters from one burn at each candidate."""
    return entropy(p_samples.mean(0)) - entropy(p_samples).mean(0)
