from enum import Enum

SUPPORTED_VARIABLES = ["temperature", "precipitation", "wind_speed"]
SUPPORTED_MODELS = ["ecmwf", "gfs", "ai", "gefs"]

class WeatherRegimeType(Enum):
    NORMAL = "NORMAL"
    HEAVY_RAIN = "HEAVY_RAIN"
    HEATWAVE = "HEATWAVE"
    HIGH_WIND = "HIGH_WIND"
    CONVECTIVE = "CONVECTIVE"
    CYCLONIC = "CYCLONIC"

class DisagreementLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    EXTREME = "EXTREME"

class UncertaintyLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"

EPSILON = 1e-10

VARIABLE_UNITS = {
    "temperature": "C",
    "precipitation": "mm",
    "wind_speed": "m/s"
}
