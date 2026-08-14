"""Judge calibration: κ against hand labels, and the cases where κ is undefined."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hoopslab.llm.judge import HumanLabel, JudgeVerdict, agreement, load_labels


def labels(*flags: bool) -> list[HumanLabel]:
    return [HumanLabel(key=f"k{i}", states_unsupported_number=flag) for i, flag in enumerate(flags)]


def predictions(keys: list[HumanLabel], *flags: bool) -> dict[str, bool]:
    return {label.key: flag for label, flag in zip(keys, flags, strict=True)}


def test_perfect_agreement_is_kappa_one() -> None:
    truth = labels(True, False, True, False)
    result = agreement(truth, predictions(truth, True, False, True, False), {})
    assert result.judge_kappa == pytest.approx(1.0)
    assert result.judge_accuracy == pytest.approx(1.0)


def test_a_detector_that_always_says_no_scores_zero_not_high() -> None:
    """The reason κ is reported instead of accuracy.

    Fabrication is rare, so "never flag anything" reaches high accuracy while
    detecting nothing. κ says so; accuracy does not.
    """
    truth = labels(True, False, False, False, False)
    result = agreement(truth, predictions(truth, False, False, False, False, False), {})
    assert result.judge_accuracy == pytest.approx(0.8)
    assert result.judge_kappa == pytest.approx(0.0)


def test_kappa_is_undefined_rather_than_zero_when_nobody_disagrees() -> None:
    """All-negative labels and an all-negative rater cannot distinguish skill."""
    truth = labels(False, False, False)
    result = agreement(truth, predictions(truth, False, False, False), {})
    assert result.judge_kappa is None
    assert "undefined" in result.render()


def test_both_detectors_are_scored_against_the_same_labels() -> None:
    truth = labels(True, True, False, False)
    result = agreement(
        truth,
        predictions(truth, True, False, False, False),  # judge misses one
        predictions(truth, True, True, False, False),  # regex catches both
    )
    assert result.regex_kappa is not None and result.judge_kappa is not None
    assert result.regex_kappa > result.judge_kappa


def test_no_labels_reports_the_absence_rather_than_a_number() -> None:
    """A judge score with no ground truth behind it is not a measurement."""
    result = agreement([], {}, {})
    assert result.n == 0
    assert "unavailable" in result.render()


def test_labels_load_from_disk(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text(
        json.dumps({"key": "abc", "states_unsupported_number": True, "notes": "quoted the pi low"}),
        encoding="utf-8",
    )
    loaded = load_labels(tmp_path)
    assert loaded == [
        HumanLabel(key="abc", states_unsupported_number=True, notes="quoted the pi low")
    ]


def test_missing_label_directory_is_empty_not_an_error(tmp_path: Path) -> None:
    assert load_labels(tmp_path / "nope") == []


def test_the_rubric_refuses_a_score_outside_one_to_four() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        JudgeVerdict(
            support=5,  # type: ignore[arg-type]
            numeric_accuracy=4,
            calibration=4,
            usefulness=4,
            states_unsupported_number=False,
        )


def test_mean_score_averages_the_four_dimensions() -> None:
    verdict = JudgeVerdict(
        support=4,
        numeric_accuracy=3,
        calibration=2,
        usefulness=3,
        states_unsupported_number=False,
    )
    assert verdict.mean_score == pytest.approx(3.0)
