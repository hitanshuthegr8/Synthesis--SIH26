from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "AIRAVAT"
    VERSION: str = "0.1.0"
    APP_ENV: str = "development"
    DEBUG: bool = False
    DEMO_MODE: bool = True
    DATABASE_URL: str = "sqlite:///./data/synthesis.db"
    DATA_DIR: str = "./data"
    RANDOM_SEED: int = 42
    GFS_ENABLED: bool = False
    GFS_BASE_URL: str = "https://nomads.ncep.noaa.gov"
    GFS_CYCLE: int = 0
    GFS_CACHE_DIR: str = "./data/gfs"
    GFS_REQUEST_TIMEOUT_SECONDS: float = 30.0
    GFS_MAX_DOWNLOAD_BYTES: int | None = None
    ECMWF_ENABLED: bool = False
    ECMWF_BASE_URL: str = "https://data.ecmwf.int/forecasts"
    ECMWF_CACHE_DIR: str = "./data/ecmwf"
    ECMWF_REQUEST_TIMEOUT_SECONDS: float = 30.0
    AIFS_ENABLED: bool = False
    AIFS_CACHE_DIR: str = "./data/aifs"
    ERA5_ENABLED: bool = False
    ERA5_CDS_URL: str = "https://cds.climate.copernicus.eu/api"
    ERA5_CDS_KEY: str | None = None
    ERA5_CACHE_DIR: str = "./data/era5"
    
    DISAGREEMENT_LOW: float = 0.10
    DISAGREEMENT_MEDIUM: float = 0.25
    DISAGREEMENT_HIGH: float = 0.50
    
    REGIME_HEAVY_RAIN_MM: float = 50.0
    REGIME_HEATWAVE_TEMP_C: float = 40.0
    REGIME_HIGH_WIND_MS: float = 20.0
    
    MINIMUM_SAMPLES: int = 30
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
