"""Public computation-trace retrieval API."""
from fastapi import APIRouter, HTTPException

from app.pipelines.forecast_cycle import ComputationTrace, cycle_registry

router = APIRouter(prefix="/api/computation", tags=["computation"])


@router.get("/{run_id}", response_model=ComputationTrace)
def get_computation(run_id: str) -> ComputationTrace:
    result = cycle_registry.get(run_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "RUN_NOT_FOUND",
                    "message": "Computation trace is not available",
                    "run_id": run_id,
                    "recoverable": False,
                }
            },
        )
    return result.trace
