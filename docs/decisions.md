# Architecture Decision Records

## ADR-001: Modular monolith over microservices
- **Title**: Modular monolith over microservices
- **Status**: Accepted
- **Context**: Need to build quickly for Phase 1 MVP without infrastructure overhead.
- **Decision**: Use a modular monolith architecture.
- **Consequences**: Faster development and easier deployment, but strict module boundaries must be enforced manually.

## ADR-002: SQLite for MVP, repository pattern for future swap
- **Title**: SQLite for MVP, repository pattern for future swap
- **Status**: Accepted
- **Context**: Need a lightweight database for local testing and demoing without complex setups.
- **Decision**: Use SQLite with the Repository pattern.
- **Consequences**: Easy setup for the MVP. May need migration to PostgreSQL later if scaling is required.

## ADR-003: Deterministic Phase 1 weighting (rule-based, not ML)
- **Title**: Deterministic Phase 1 weighting (rule-based, not ML)
- **Status**: Accepted
- **Context**: ML models require extensive training data and time, which is out of scope for the Phase 1 MVP.
- **Decision**: Implement rule-based heuristics for weighting models.
- **Consequences**: Highly interpretable and fast to implement, but perhaps less accurate than advanced ML.

## ADR-004: Interpretable weather regime engine (threshold-based)
- **Title**: Interpretable weather regime engine (threshold-based)
- **Status**: Accepted
- **Context**: Need to classify weather regimes to adjust blending weights dynamically.
- **Decision**: Use simple threshold-based classification (e.g., Temp > 30C = Hot).
- **Consequences**: Easy to explain to end-users and implement.

## ADR-005: Demo mode is fully offline
- **Title**: Demo mode is fully offline
- **Status**: Accepted
- **Context**: System must be demonstrable without external API dependencies or active internet connection.
- **Decision**: Pre-seed the database with offline demo data.
- **Consequences**: Guaranteed working demo in any environment, but data is static.

## ADR-006: No unsupported performance claims
- **Title**: No unsupported performance claims
- **Status**: Accepted
- **Context**: Scientific integrity is paramount in weather forecasting tools.
- **Decision**: Clearly state the limitations of the Phase 1 MVP and avoid unsupported performance claims.
- **Consequences**: Manages expectations appropriately and builds trust.

## ADR-007: Phase 2 ML interfaces via Python Protocol classes
- **Title**: Phase 2 ML interfaces via Python Protocol classes
- **Status**: Accepted
- **Context**: Need a clear path to upgrade from rule-based to ML-based weighting in Phase 2.
- **Decision**: Define strict Python `Protocol` interfaces for core engine components.
- **Consequences**: Ensures future ML modules can seamlessly integrate without breaking existing code.
