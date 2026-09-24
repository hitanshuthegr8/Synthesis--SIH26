"""Pure, dependency-free error metrics used by verification and skill scoring."""
import math
from collections.abc import Sequence
from pydantic import BaseModel, Field, field_validator


class SkillMetrics(BaseModel):
    """Comparable error summary for one model and one forecast context."""

    mae: float = Field(ge=0.0)
    rmse: float = Field(ge=0.0)
    bias: float
    sample_count: int = Field(gt=0)

    @field_validator("mae", "rmse", "bias")
    @classmethod
    def values_must_be_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Metric values must be finite")
        return value


def calculate_mae(predictions: Sequence[float], observations: Sequence[float]) -> float:
    errors = _errors(predictions, observations)
    return sum(abs(error) for error in errors) / len(errors)


def calculate_rmse(predictions: Sequence[float], observations: Sequence[float]) -> float:
    errors = _errors(predictions, observations)
    return math.sqrt(sum(error**2 for error in errors) / len(errors))


def calculate_bias(predictions: Sequence[float], observations: Sequence[float]) -> float:
    errors = _errors(predictions, observations)
    return sum(errors) / len(errors)


def calculate_skill_metrics(predictions: Sequence[float], observations: Sequence[float]) -> SkillMetrics:
    errors = _errors(predictions, observations)
    return SkillMetrics(
        mae=sum(abs(error) for error in errors) / len(errors),
        rmse=math.sqrt(sum(error**2 for error in errors) / len(errors)),
        bias=sum(errors) / len(errors),
        sample_count=len(errors),
    )


def _errors(predictions: Sequence[float], observations: Sequence[float]) -> list[float]:
    if not predictions:
        raise ValueError("At least one prediction-observation pair is required")
    if len(predictions) != len(observations):
        raise ValueError("Predictions and observations must have equal length")
    errors = [float(prediction) - float(observation) for prediction, observation in zip(predictions, observations)]
    if not all(math.isfinite(error) for error in errors):
        raise ValueError("Predictions and observations must be finite")
    return errors
