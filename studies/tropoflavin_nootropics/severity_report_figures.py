"""Legible scientific figures drawn only from validated aggregate records."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from studies.tropoflavin_nootropics.severity_report_data import wilson_interval

if TYPE_CHECKING:
    from studies.tropoflavin_nootropics.publish_severity_reports import Checkpoint


def render_figures(data: Checkpoint, directory: Path) -> tuple[Path, ...]:
    """Render readable PNGs with denominators and uncertainty stated on the figure."""
    plt.rcParams.update(
        {
            "font.size": 12,
            "axes.titlesize": 14,
            "axes.labelsize": 12,
            "savefig.dpi": 180,
        }
    )
    outputs: list[Path] = []
    summaries = [
        row
        for row in data.summaries
        if row.scope == "all communities, globally deduplicated"
    ]
    positions = np.arange(len(summaries))
    fig, axes = plt.subplots(1, 2, figsize=(14, 7.8), sharey=True)
    for axis, conditional in zip(axes, (False, True), strict=True):
        values, lows, highs = [], [], []
        for row in summaries:
            denominator = (
                row.authors_with_explicit_severity if conditional else row.authors
            )
            numerator = row.authors_with_explicit_moderate_or_worse
            lower, upper = wilson_interval(numerator, denominator)
            value = 100 * numerator / denominator
            values.append(value)
            lows.append(value - 100 * lower)
            highs.append(100 * upper - value)
            axis.annotate(
                f"{numerator}/{denominator}",
                (100 * upper, len(values) - 1),
                xytext=(6, 0),
                textcoords="offset points",
                va="center",
                fontsize=10,
            )
        axis.errorbar(
            values,
            positions,
            xerr=[lows, highs],
            fmt="o",
            capsize=4,
            color="#215478",
            markersize=7,
        )
        axis.set_title(
            "Among authors with an explicit grade"
            if conditional
            else "Among all classified authors",
            pad=12,
        )
        axis.set_xlabel("Authors with a documented moderate+ effect (%)")
        axis.set_xlim(
            0,
            107
            if conditional
            else max(value + high for value, high in zip(values, highs, strict=True))
            * 1.4,
        )
        axis.grid(axis="x", color="#dddddd")
        axis.set_axisbelow(True)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].set_yticks(positions, [row.compound for row in summaries])
    axes[0].invert_yaxis()
    fig.suptitle("Explicit moderate-or-worse side-effect reports", fontsize=19, y=0.99)
    fig.text(
        0.5,
        0.025,
        "95% Wilson intervals. Different denominators and axis ranges. Unknown severity is not imputed.\nFrozen Sep 3 checkpoint; self-selected online reports, not clinical incidence.",
        ha="center",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0.09, 1, 0.95), w_pad=3)
    path = directory / "severity_moderate_or_worse.png"
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    outputs.append(path)

    eligibility = data.linear_eligibility
    positions = np.arange(len(eligibility))
    fig, axis = plt.subplots(figsize=(13, 7.5))
    for offset, field, label, color in (
        (-0.24, "explicit_severity_authors", "Explicit severity", "#215478"),
        (0, "dose_model_authors", "Severity + usable dose", "#e79737"),
        (0.24, "dose_and_route_model_authors", "Severity + dose + route", "#489b7c"),
    ):
        values = [getattr(row, field) for row in eligibility]
        axis.barh(positions + offset, values, height=0.21, color=color, label=label)
        for position, value in zip(positions + offset, values, strict=True):
            axis.text(value + 2, position, str(value), va="center", fontsize=10)
    axis.set_yticks(positions, [row.compound for row in eligibility])
    axis.invert_yaxis()
    axis.set_xlim(0, max(row.explicit_severity_authors for row in eligibility) * 1.16)
    axis.set_xlabel("Globally deduplicated authors per compound")
    axis.set_title(
        "Explicit severity is rarely linked to usable dose and route", pad=16
    )
    axis.legend(loc="lower right", frameon=False, fontsize=11)
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(axis="x", color="#dddddd")
    axis.set_axisbelow(True)
    fig.text(
        0.5,
        0.025,
        "Frozen Sep 3 linear-model eligibility, before rare-route filtering. Author-history links are not necessarily same-episode links.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=(0, 0.055, 1, 1))
    path = directory / "severity_eligibility.png"
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    outputs.append(path)

    coefficients = data.moderate_coefficients
    fig, axis = plt.subplots(figsize=(12.5, 5.8))
    positions = np.arange(len(coefficients))
    values = [row.odds_ratio for row in coefficients]
    errors = [
        [row.odds_ratio - row.odds_ratio_95_ci_low for row in coefficients],
        [row.odds_ratio_95_ci_high - row.odds_ratio for row in coefficients],
    ]
    labels = [
        f"{row.compound}: {row.model}\n{row.term}; n={row.authors}"
        for row in coefficients
    ]
    axis.errorbar(
        values,
        positions,
        xerr=errors,
        fmt="o",
        color="#215478",
        capsize=5,
        markersize=8,
    )
    axis.axvline(1, linestyle="--", color="#888888")
    axis.set_xscale("log")
    axis.set_xlim(0.08, 7)
    axis.set_xticks([0.1, 0.25, 0.5, 1, 2, 4], ["0.1", "0.25", "0.5", "1", "2", "4"])
    axis.set_yticks(positions, labels)
    axis.invert_yaxis()
    axis.set_xlabel("Odds ratio for at least one moderate+ effect (95% robust CI)")
    axis.set_title("Conditional moderate+ associations remain uncertain", pad=16)
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(axis="x", color="#dddddd")
    axis.set_axisbelow(True)
    fig.text(
        0.5,
        0.02,
        "Among authors with an explicitly graded effect. Model samples differ; route reference is parenteral.\nFrozen Sep 3 checkpoint. No estimable 7,8-DHF severity model; these associations are not causal predictions.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=(0, 0.10, 1, 1))
    path = directory / "severity_moderate_models.png"
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    outputs.append(path)
    return tuple(outputs)
