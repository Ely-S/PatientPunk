"""Estimators shared by the analysis. All take a daily count Series indexed by date."""
import numpy as np, pandas as pd
from scipy import stats

START, END = "2020-08-01", "2025-11-11"   # window both sources cover in full


def full_index(s, start=START, end=END):
    idx = pd.date_range(start, end, freq="D")
    return s.reindex(idx, fill_value=0).astype(float)


def alpha(y, expo=None, blocks=None):
    """Extra-Poisson variance of the latent daily rate, relative to its monthly level.

    Model: y_t ~ Poisson(lambda_t), lambda_t = m_B * e_t * (1 + eps_t), Var(eps) = alpha.
    m_B is the month level, e_t an optional exposure (e.g. total subreddit activity that day,
    normalised within the month). Method of moments, pooled over months:
        alpha = sum((y - mu)^2 * k - mu) / sum(mu^2),  mu = expected count, k = n/(n-1).
    sqrt(alpha) is the day-to-day coefficient of variation of attention that Poisson noise
    cannot explain. 0 = steady; 1 = a typical day is +/-100% off its month's level.
    """
    y = np.asarray(y, float)
    e = np.ones_like(y) if expo is None else np.asarray(expo, float)
    b = blocks
    num = den = 0.0
    for g in np.unique(b):
        m = b == g
        yy, ee = y[m], e[m]
        if yy.sum() == 0 or len(yy) < 2:
            continue
        ee = ee / ee.mean()
        mu = yy.mean() * ee
        k = len(yy) / (len(yy) - 1)
        num += ((yy - mu) ** 2 * k - mu).sum()
        den += (mu ** 2).sum()
    return num / den if den else np.nan


def alpha_boot(y, expo=None, n=2000, seed=0):
    """alpha with a 95% CI from a bootstrap over months (months resampled whole)."""
    y = pd.Series(y)
    months = y.index.to_period("M").astype(str).values
    est = alpha(y.values, None if expo is None else expo.values, months)
    uniq = np.unique(months)
    groups = {g: np.where(months == g)[0] for g in uniq}
    rng = np.random.default_rng(seed)
    yv = y.values; ev = None if expo is None else expo.values
    bs = []
    for _ in range(n):
        pick = rng.choice(uniq, len(uniq))
        ix = np.concatenate([groups[g] for g in pick])
        lab = np.concatenate([np.full(len(groups[g]), i) for i, g in enumerate(pick)])
        bs.append(alpha(yv[ix], None if ev is None else ev[ix], lab))
    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
    return est, lo, hi, np.array(bs)


def baseline(y, half=14):
    """Robust local level: median of the 2*half surrounding days, the day itself excluded.
    Falls back to the mean of those days without their 3 largest when the median is 0."""
    v = np.asarray(y, float); n = len(v); out = np.empty(n)
    for i in range(n):
        w = np.concatenate([v[max(0, i - half):i], v[i + 1:i + 1 + half]])
        med = np.median(w)
        out[i] = med if med > 0 else max(np.sort(w)[:-3].mean() if len(w) > 3 else 0, 1 / (2 * half))
    return pd.Series(out, index=y.index)


def spikes(y, b=None, p=1e-3, fold=3.0):
    """Days far above their local level: Poisson tail p < 1e-3 and at least 3x baseline."""
    b = baseline(y) if b is None else b
    pv = stats.poisson.sf(y.values - 1, b.values)
    flag = (pv < p) & (y.values >= fold * b.values)
    return pd.Series(flag, index=y.index), b


def spike_share(y):
    """Share of all posts that are excess over baseline on spike days."""
    f, b = spikes(y)
    excess = (y - b).clip(lower=0)[f].sum()
    return excess / y.sum(), int(f.sum())


def top_share(y, q=0.01):
    k = max(1, int(round(len(y) * q)))
    return np.sort(y.values)[::-1][:k].sum() / y.sum()


def rate_ratio_ci(n1, t1, n0, t0, conf=0.95):
    """Exact (conditional binomial) CI for a Poisson rate ratio (n1/t1)/(n0/t0)."""
    a = (1 - conf) / 2; n = n1 + n0
    lo = stats.beta.ppf(a, n1, n0 + 1) if n1 > 0 else 0.0
    hi = stats.beta.ppf(1 - a, n1 + 1, n0) if n0 > 0 else np.inf
    f = lambda p: p / (1 - p) * t0 / t1
    return (n1 / t1) / (n0 / t0), f(lo), f(hi)

