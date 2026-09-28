"""TASK 003 — Domain schema tests.

Tests all domain models for:
- Valid construction
- Field validation (physical constraints)
- Invalid input rejection (NaN, Inf, out-of-range, missing fields)
- Mathematical invariants (weights sum to 1, probabilities sum to 1, bounds ordering)
"""
import math
from datetime import datetime

import pytest

from app.domain.forecast import Forecast, Observation
from app.domain.model import ModelSkill
from app.domain.regime import WeatherRegime
from app.domain.uncertainty import (
    DisagreementResult,
    UncertaintyEstimate,
    BlendResult,
)
from app.domain.verification import VerificationResult, ForecastAutopsy
from app.core.constants import WeatherRegimeType, DisagreementLevel, UncertaintyLevel


# ── Forecast Tests ──────────────────────────────────────────────────────────


class TestForecast:
    """Test Forecast domain model."""

    def _make_forecast(self, **overrides) -> Forecast:
        defaults = dict(
            model_id="ecmwf",
            variable="temperature",
            latitude=19.07,
            longitude=72.87,
            initialization_time=datetime(2026, 9, 24),
            lead_hours=48,
            value=31.4,
            unit="C",
        )
        defaults.update(overrides)
        return Forecast(**defaults)

    def test_valid_forecast(self) -> None:
        f = self._make_forecast()
        assert f.model_id == "ecmwf"
        assert f.value == 31.4

    def test_invalid_variable(self) -> None:
        with pytest.raises(ValueError, match="Unsupported variable"):
            self._make_forecast(variable="humidity")

    def test_invalid_latitude_too_high(self) -> None:
        with pytest.raises(ValueError):
            self._make_forecast(latitude=91.0)

    def test_invalid_latitude_too_low(self) -> None:
        with pytest.raises(ValueError):
            self._make_forecast(latitude=-91.0)

    def test_invalid_longitude(self) -> None:
        with pytest.raises(ValueError):
            self._make_forecast(longitude=181.0)

    def test_negative_lead_hours(self) -> None:
        with pytest.raises(ValueError):
            self._make_forecast(lead_hours=-1)

    def test_nan_value(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            self._make_forecast(value=float("nan"))

    def test_inf_value(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            self._make_forecast(value=float("inf"))

    def test_empty_model_id(self) -> None:
        with pytest.raises(ValueError):
            self._make_forecast(model_id="")

    def test_boundary_latitude(self) -> None:
        f = self._make_forecast(latitude=90.0)
        assert f.latitude == 90.0
        f = self._make_forecast(latitude=-90.0)
        assert f.latitude == -90.0

    def test_zero_lead_hours(self) -> None:
        f = self._make_forecast(lead_hours=0)
        assert f.lead_hours == 0

    def test_precipitation_variable(self) -> None:
        f = self._make_forecast(variable="precipitation", value=42.0, unit="mm")
        assert f.variable == "precipitation"

    def test_wind_speed_variable(self) -> None:
        f = self._make_forecast(variable="wind_speed", value=15.0, unit="m/s")
        assert f.variable == "wind_speed"


# ── Observation Tests ───────────────────────────────────────────────────────


class TestObservation:
    """Test Observation domain model."""

    def _make_observation(self, **overrides) -> Observation:
        defaults = dict(
            variable="temperature",
            latitude=19.07,
            longitude=72.87,
            valid_time=datetime(2026, 9, 26),
            value=33.1,
            unit="C",
        )
        defaults.update(overrides)
        return Observation(**defaults)

    def test_valid_observation(self) -> None:
        o = self._make_observation()
        assert o.value == 33.1

    def test_invalid_variable(self) -> None:
        with pytest.raises(ValueError, match="Unsupported variable"):
            self._make_observation(variable="pressure")

    def test_nan_value(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            self._make_observation(value=float("nan"))


# ── ModelSkill Tests ────────────────────────────────────────────────────────


class TestModelSkill:
    """Test ModelSkill domain model."""

    def _make_skill(self, **overrides) -> ModelSkill:
        defaults = dict(
            model_id="ecmwf",
            variable="temperature",
            lead_hours=48,
            metric="mae",
            score=2.1,
            sample_count=4812,
        )
        defaults.update(overrides)
        return ModelSkill(**defaults)

    def test_valid_skill(self) -> None:
        s = self._make_skill()
        assert s.score == 2.1
        assert s.sample_count == 4812

    def test_negative_sample_count(self) -> None:
        with pytest.raises(ValueError):
            self._make_skill(sample_count=-1)

    def test_nan_score(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            self._make_skill(score=float("nan"))

    def test_inf_score(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            self._make_skill(score=float("inf"))

    def test_default_region(self) -> None:
        s = self._make_skill()
        assert s.region == "global"

    def test_optional_season(self) -> None:
        s = self._make_skill(season="JJA")
        assert s.season == "JJA"

    def test_optional_regime(self) -> None:
        s = self._make_skill(regime="HEAVY_RAIN")
        assert s.regime == "HEAVY_RAIN"


# ── WeatherRegime Tests ────────────────────────────────────────────────────


class TestWeatherRegime:
    """Test WeatherRegime domain model."""

    def _make_regime(self, **overrides) -> WeatherRegime:
        defaults = dict(
            name=WeatherRegimeType.HEAVY_RAIN,
            confidence=0.81,
            probabilities={
                "NORMAL": 0.05,
                "HEAVY_RAIN": 0.81,
                "HEATWAVE": 0.02,
                "HIGH_WIND": 0.04,
                "CONVECTIVE": 0.08,
                "CYCLONIC": 0.00,
            },
        )
        defaults.update(overrides)
        return WeatherRegime(**defaults)

    def test_valid_regime(self) -> None:
        r = self._make_regime()
        assert r.name == WeatherRegimeType.HEAVY_RAIN
        assert r.confidence == 0.81

    def test_probabilities_must_sum_to_one(self) -> None:
        with pytest.raises(ValueError, match="sum to"):
            self._make_regime(
                probabilities={"NORMAL": 0.5, "HEAVY_RAIN": 0.1}
            )

    def test_negative_probability(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            self._make_regime(
                probabilities={
                    "NORMAL": -0.1,
                    "HEAVY_RAIN": 1.1,
                }
            )

    def test_empty_probabilities(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            self._make_regime(probabilities={})

    def test_confidence_matches_primary(self) -> None:
        with pytest.raises(ValueError, match="doesn't match"):
            self._make_regime(
                confidence=0.50,
                probabilities={
                    "NORMAL": 0.19,
                    "HEAVY_RAIN": 0.81,
                },
            )

    def test_confidence_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            self._make_regime(confidence=1.5)


# ── DisagreementResult Tests ───────────────────────────────────────────────


class TestDisagreementResult:
    """Test DisagreementResult domain model."""

    def test_valid_disagreement(self) -> None:
        d = DisagreementResult(
            mean=34.5,
            std=14.8,
            min_value=18.0,
            max_value=53.0,
            range=35.0,
            level=DisagreementLevel.HIGH,
            model_count=4,
        )
        assert d.level == DisagreementLevel.HIGH

    def test_negative_std(self) -> None:
        with pytest.raises(ValueError):
            DisagreementResult(
                mean=34.5,
                std=-1.0,
                min_value=18.0,
                max_value=53.0,
                range=35.0,
                level=DisagreementLevel.LOW,
                model_count=4,
            )

    def test_zero_disagreement(self) -> None:
        d = DisagreementResult(
            mean=30.0,
            std=0.0,
            min_value=30.0,
            max_value=30.0,
            range=0.0,
            level=DisagreementLevel.LOW,
            model_count=4,
        )
        assert d.range == 0.0
        assert d.std == 0.0


# ── UncertaintyEstimate Tests ──────────────────────────────────────────────


class TestUncertaintyEstimate:
    """Test UncertaintyEstimate domain model."""

    def test_valid_uncertainty(self) -> None:
        u = UncertaintyEstimate(
            forecast_value=42.0,
            lower_bound=24.0,
            upper_bound=67.0,
            level=UncertaintyLevel.HIGH,
        )
        assert u.lower_bound == 24.0
        assert u.upper_bound == 67.0

    def test_upper_below_lower(self) -> None:
        with pytest.raises(ValueError, match="Upper bound"):
            UncertaintyEstimate(
                forecast_value=42.0,
                lower_bound=67.0,
                upper_bound=24.0,
                level=UncertaintyLevel.HIGH,
            )


# ── BlendResult Tests ──────────────────────────────────────────────────────


class TestBlendResult:
    """Test BlendResult domain model — the primary output of AIRAVAT."""

    def _make_blend(self, **overrides) -> BlendResult:
        defaults = dict(
            variable="precipitation",
            latitude=19.07,
            longitude=72.87,
            valid_time="2026-09-26T00:00:00Z",
            blended_value=43.7,
            lower_bound=24.0,
            upper_bound=68.0,
            model_weights={"ecmwf": 0.44, "gfs": 0.14, "ai": 0.32, "gefs": 0.10},
            disagreement=DisagreementResult(
                mean=38.75,
                std=16.0,
                min_value=21.0,
                max_value=57.0,
                range=36.0,
                level=DisagreementLevel.HIGH,
                model_count=4,
            ),
            regime="HEAVY_RAIN",
            regime_confidence=0.82,
            explanation=["ECMWF received the highest weight."],
            fallback_mode=False,
            run_id="test-run-001",
        )
        defaults.update(overrides)
        return BlendResult(**defaults)

    def test_valid_blend(self) -> None:
        b = self._make_blend()
        assert b.blended_value == 43.7
        assert b.fallback_mode is False

    def test_weights_must_sum_to_one(self) -> None:
        with pytest.raises(ValueError, match="sum to"):
            self._make_blend(
                model_weights={"ecmwf": 0.5, "gfs": 0.1}
            )

    def test_negative_weight(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            self._make_blend(
                model_weights={"ecmwf": -0.1, "gfs": 1.1}
            )

    def test_upper_below_lower(self) -> None:
        with pytest.raises(ValueError, match="Upper bound"):
            self._make_blend(lower_bound=70.0, upper_bound=20.0)

    def test_single_model_fallback(self) -> None:
        b = self._make_blend(
            model_weights={"ecmwf": 1.0},
            fallback_mode=True,
        )
        assert b.fallback_mode is True
        assert b.model_weights["ecmwf"] == 1.0


# ── VerificationResult Tests ──────────────────────────────────────────────


class TestVerificationResult:
    """Test VerificationResult domain model."""

    def test_valid_verification(self) -> None:
        v = VerificationResult(
            run_id="run-001",
            variable="precipitation",
            latitude=19.07,
            longitude=72.87,
            valid_time=datetime(2026, 9, 26),
            forecast_value=42.0,
            observation_value=67.0,
            error=-25.0,
            absolute_error=25.0,
            model_errors={"ecmwf": -31.0, "gfs": -40.0, "ai": -18.0},
            regime="HEAVY_RAIN",
            lead_hours=48,
        )
        assert v.error == -25.0

    def test_nan_error(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            VerificationResult(
                run_id="run-001",
                variable="precipitation",
                latitude=19.07,
                longitude=72.87,
                valid_time=datetime(2026, 9, 26),
                forecast_value=float("nan"),
                observation_value=67.0,
                error=-25.0,
                absolute_error=25.0,
                lead_hours=48,
            )
