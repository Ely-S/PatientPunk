"""
roster_exec.py — fast, rate-limit-aware parallel execution for roster sweeps.

The shared runner for every judgement harness (①②③…). Two ideas make a 20-model sweep
finish in minutes instead of tens of minutes:

  1. INTERLEAVE by key (model): round-robin the task queue so the concurrent in-flight
     set spans many models, instead of hammering one provider's rate limit at a time.
  2. PER-KEY CONCURRENCY CAP: allow high TOTAL concurrency (dozens of calls in flight)
     but at most `per_key` simultaneous calls to any single model — so one provider's
     429s can't throttle the whole sweep, and fast cheap models aren't stuck behind a
     slow flagship.

Usage:
    from roster_exec import parallel_map
    results = parallel_map(run_one, tasks, workers=40, per_key=3,
                           key=lambda t: t.model, progress="generation")
"""
from __future__ import annotations

import sys
import threading
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterable


def interleave(tasks: list, key: Callable) -> list:
    """Round-robin the tasks across their keys so consecutive tasks use different keys."""
    buckets: dict = defaultdict(deque)
    for t in tasks:
        buckets[key(t)].append(t)
    queues = list(buckets.values())
    out = []
    while any(queues):
        for q in queues:
            if q:
                out.append(q.popleft())
    return out


def parallel_map(
    fn: Callable,
    tasks: Iterable,
    *,
    workers: int = 40,
    per_key: int = 3,
    key: Callable | None = None,
    progress: str | None = None,
    progress_every: int = 50,
) -> list:
    """Run fn(task) across tasks concurrently and return results in completion order.

    workers   — max total concurrent calls in flight.
    per_key   — max concurrent calls sharing the same key(task) (e.g. same model).
    key       — task -> hashable group (default: everything one group).
    progress  — if set, print "<progress> i/n" every `progress_every` (flushed).

    fn should catch its own exceptions and return a sentinel on failure; an uncaught
    exception in fn will surface when its result is collected and abort the run.
    """
    tasks = list(tasks)
    key = key or (lambda _t: None)
    ordered = interleave(tasks, key)
    sems: dict = {k: threading.Semaphore(per_key) for k in {key(t) for t in tasks}}

    def gated(t):
        s = sems[key(t)]
        s.acquire()
        try:
            return fn(t)
        finally:
            s.release()

    results, n = [], len(ordered)
    # workers above the per_key*num_keys ceiling just wastes threads; cap it there.
    eff_workers = max(1, min(workers, per_key * max(1, len(sems))))
    with ThreadPoolExecutor(max_workers=eff_workers) as pool:
        futs = [pool.submit(gated, t) for t in ordered]
        for i, f in enumerate(as_completed(futs), 1):
            results.append(f.result())
            if progress and (i % progress_every == 0 or i == n):
                print(f"  {progress} {i}/{n}", flush=True)
    return results
