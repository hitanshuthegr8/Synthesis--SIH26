import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def offline_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the suite offline even when a local .env enables live providers; tests opt in explicitly."""
    for flag in ("GFS_ENABLED", "ECMWF_ENABLED", "AIFS_ENABLED", "ERA5_ENABLED"):
        monkeypatch.setattr(settings, flag, False)
