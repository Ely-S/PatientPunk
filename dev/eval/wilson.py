"""Wilson score interval + disjoint-CI contrast — stdlib only.

The portable, faithful core of the dr-hiro MEASURED methodology: every rate we
report is a Bernoulli proportion (k successes out of n trials) and we attach a
Wilson 95% confidence interval rather than a bare point estimate. Two rates are
called SEPARATED only when their Wilson intervals are disjoint — the
methodology's conservative substitute for a significance test.

No numpy/scipy: the Wilson formula is closed-form and needs only math.sqrt.
"""
from __future__ import annotations

import math


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Wilson score interval for k successes in n trials.

    Returns (p_hat, lo, hi) where p_hat = k/n is the point estimate and
    [lo, hi] is the two-sided Wilson interval at confidence implied by z
    (z=1.96 -> ~95%). For n == 0 returns (0.0, 0.0, 1.0): no data means the
    rate is wholly unknown, so the interval spans the full [0, 1] range.

    The Wilson interval is preferred over the normal (Wald) interval because it
    stays inside [0, 1] and behaves well for small n and extreme p (k=0 or k=n),
    which is exactly the small-sample regime this eval lives in.
    """
    if n <= 0:
        return (0.0, 0.0, 1.0)
    if k < 0 or k > n:
        raise ValueError(f"k={k} out of range for n={n}")
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / denom
    lo = center - margin
    hi = center + margin
    # Clamp for floating-point spill outside [0, 1].
    return (p, max(0.0, lo), min(1.0, hi))


def rule_of_three(n: int) -> float:
    """Rule of three: 3/n.

    When k == 0 (zero observed failures/successes in n trials) the upper bound
    on the true rate is ~3/n at 95% confidence. Handy sanity check for "never
    saw it fail" claims — if n is small, 3/n is large, i.e. you cannot conclude
    the true rate is low. Returns 1.0 for n == 0 (no information).
    """
    if n <= 0:
        return 1.0
    return 3.0 / n


def contrast(ka: int, na: int, kb: int, nb: int, z: float = 1.96) -> str:
    """Compare two proportions via their Wilson intervals.

    Returns "SEPARATED" iff the two Wilson CIs are disjoint (one interval's
    lower bound exceeds the other's upper bound), else "overlap". This is the
    methodology's conservative gate: only call a difference real when the
    intervals do not touch.
    """
    _, lo_a, hi_a = wilson(ka, na, z)
    _, lo_b, hi_b = wilson(kb, nb, z)
    if hi_a < lo_b or hi_b < lo_a:
        return "SEPARATED"
    return "overlap"
