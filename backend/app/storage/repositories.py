"""Typed SQLite repository methods; core engines never depend on SQL rows."""
from collections.abc import Sequence

from app.domain.forecast import Forecast, Observation
from app.domain.model import ModelSkill
from app.domain.uncertainty import BlendResult
from app.domain.verification import VerificationResult
from app.storage.database import SQLiteDatabase


class SynthesisRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database
        self.database.initialize()

    def save_forecasts(self, forecasts: Sequence[Forecast]) -> None:
        self._save_many("forecasts", forecasts)

    def save_observations(self, observations: Sequence[Observation]) -> None:
        self._save_many("observations", observations)

    def save_model_skills(self, skills: Sequence[ModelSkill]) -> None:
        self._save_many("model_skills", skills)

    def save_blend(self, blend: BlendResult) -> None:
        self._upsert("blend_results", blend.run_id, blend)

    def save_verification(self, verification: VerificationResult) -> None:
        self._upsert("verification_results", verification.run_id, verification)

    def save_forecast_cycle(self, run_id: str, payload: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO forecast_cycles (run_id, payload) VALUES (?, ?) "
                "ON CONFLICT(run_id) DO UPDATE SET payload=excluded.payload",
                (run_id, payload),
            )

    def list_forecasts(self) -> list[Forecast]:
        return self._load_many("forecasts", Forecast)

    def list_observations(self) -> list[Observation]:
        return self._load_many("observations", Observation)

    def list_model_skills(self) -> list[ModelSkill]:
        return self._load_many("model_skills", ModelSkill)

    def get_blend(self, run_id: str) -> BlendResult | None:
        return self._get_one("blend_results", run_id, BlendResult)

    def get_verification(self, run_id: str) -> VerificationResult | None:
        return self._get_one("verification_results", run_id, VerificationResult)

    def get_forecast_cycle(self, run_id: str) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM forecast_cycles WHERE run_id = ?", (run_id,)
            ).fetchone()
        return row["payload"] if row else None

    def get_latest_forecast_cycle(self) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM forecast_cycles ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
        return row["payload"] if row else None

    def _save_many(self, table: str, models: Sequence[object]) -> None:
        with self.database.connect() as connection:
            connection.executemany(
                f"INSERT INTO {table} (payload) VALUES (?)",
                [(model.model_dump_json(),) for model in models],
            )

    def _upsert(self, table: str, identifier: str, model: object) -> None:
        with self.database.connect() as connection:
            connection.execute(
                f"INSERT INTO {table} (run_id, payload) VALUES (?, ?) ON CONFLICT(run_id) DO UPDATE SET payload=excluded.payload",
                (identifier, model.model_dump_json()),
            )

    def _load_many(self, table: str, model_type: type) -> list[object]:
        with self.database.connect() as connection:
            rows = connection.execute(f"SELECT payload FROM {table} ORDER BY id").fetchall()
        return [model_type.model_validate_json(row["payload"]) for row in rows]

    def _get_one(self, table: str, identifier: str, model_type: type) -> object | None:
        with self.database.connect() as connection:
            row = connection.execute(f"SELECT payload FROM {table} WHERE run_id = ?", (identifier,)).fetchone()
        return model_type.model_validate_json(row["payload"]) if row else None
