# Development Guide

## Prerequisites
- Python 3.11+
- Node.js 20+
- Docker (optional, for quick start)

## Setup Instructions
Clone the repository and follow the backend/frontend setup instructions in the README.

## Running Tests
```bash
cd backend
pytest
```

## Running the Backend
```bash
cd backend
uvicorn main:app --reload
```

## Running the Frontend
```bash
cd frontend
npm run dev
```

## Code Style
- Use strict type hints (`typing` module) in all Python code.
- Validate data heavily using `pydantic`.
- Keep functions small, focused, and testable.
- Document logic clearly with docstrings.

## Testing Strategy
- Unit Tests: For core logic (weighting, blending).
- Schema Tests: To ensure Pydantic models behave as expected.
- Integration Tests: Testing database queries and flows.
- API Tests: Endpoint behavior (FastAPI TestClient).

## Micro-task Development Protocol
Follow a test-driven approach: write tests for expected behavior, implement logic to pass, refactor while keeping tests green. Commit frequently.
