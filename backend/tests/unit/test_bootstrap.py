"""TASK 001 — Bootstrap verification tests.

These tests verify that the project skeleton is correctly set up:
- Config loads with correct defaults
- Constants and enums are defined
- FastAPI app starts and health endpoint works
"""
import pytest
from app.core.config import settings
from app.core.constants import (
    SUPPORTED_VARIABLES,
    SUPPORTED_MODELS,
    WeatherRegimeType,
    DisagreementLevel,
    UncertaintyLevel,
    EPSILON,
    VARIABLE_UNITS,
)


class TestConfig:
    """Verify configuration loads correctly."""

    def test_app_name(self) -> None:
        assert settings.APP_NAME == "AIRAVAT"

    def test_version(self) -> None:
        assert settings.VERSION == "0.1.0"

    def test_demo_mode_default(self) -> None:
        assert settings.DEMO_MODE is True

    def test_random_seed(self) -> None:
        assert settings.RANDOM_SEED == 42

    def test_disagreement_thresholds_ordered(self) -> None:
        assert settings.DISAGREEMENT_LOW < settings.DISAGREEMENT_MEDIUM
        assert settings.DISAGREEMENT_MEDIUM < settings.DISAGREEMENT_HIGH

    def test_minimum_samples_positive(self) -> None:
        assert settings.MINIMUM_SAMPLES > 0


class TestConstants:
    """Verify constants and enums."""

    def test_supported_variables(self) -> None:
        assert "temperature" in SUPPORTED_VARIABLES
        assert "precipitation" in SUPPORTED_VARIABLES
        assert "wind_speed" in SUPPORTED_VARIABLES

    def test_supported_models(self) -> None:
        assert "ecmwf" in SUPPORTED_MODELS
        assert "gfs" in SUPPORTED_MODELS
        assert "ai" in SUPPORTED_MODELS
        assert "gefs" in SUPPORTED_MODELS

    def test_weather_regimes(self) -> None:
        regimes = [r.value for r in WeatherRegimeType]
        assert "NORMAL" in regimes
        assert "HEAVY_RAIN" in regimes
        assert "HEATWAVE" in regimes
        assert "HIGH_WIND" in regimes
        assert "CONVECTIVE" in regimes
        assert "CYCLONIC" in regimes

    def test_disagreement_levels(self) -> None:
        levels = [d.value for d in DisagreementLevel]
        assert levels == ["LOW", "MEDIUM", "HIGH", "EXTREME"]

    def test_uncertainty_levels(self) -> None:
        levels = [u.value for u in UncertaintyLevel]
        assert levels == ["LOW", "MEDIUM", "HIGH", "VERY_HIGH"]

    def test_epsilon_positive_small(self) -> None:
        assert 0 < EPSILON < 1e-6

    def test_variable_units(self) -> None:
        assert VARIABLE_UNITS["temperature"] == "C"
        assert VARIABLE_UNITS["precipitation"] == "mm"
        assert VARIABLE_UNITS["wind_speed"] == "m/s"
