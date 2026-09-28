"""Guard: dashboard must not embed scientific metrics as React constants."""
import re
from pathlib import Path

FRONTEND_SRC = Path(__file__).resolve().parents[3] / "frontend" / "src"

# Labels that should not appear beside hard-coded numeric literals in TSX.
FORBIDDEN_CONTEXT = re.compile(
    r"(MAE|RMSE|CSI|skill|weight|uncertainty|accuracy|blended_value|model_weights)\s*[:=]\s*\{?\s*\d+\.\d+",
    re.IGNORECASE,
)

ALLOWLIST_SNIPPETS = (
    "rel=1e-6",
    "block_until_ms",
    "font-size",
    "letter-spacing",
    "width:",
    "height:",
    "padding",
    "margin",
    "gap:",
    "z-index",
    "opacity",
    "duration_ms",
    "lead_hours",
    "ge=0",
)


def test_frontend_has_no_hardcoded_metric_literals() -> None:
    assert FRONTEND_SRC.is_dir(), "frontend/src must exist"
    violations: list[str] = []
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in {".tsx", ".ts", ".jsx", ".js"}:
            continue
        text = path.read_text(encoding="utf-8")
        for match in FORBIDDEN_CONTEXT.finditer(text):
            snippet = text[max(0, match.start() - 40) : match.end() + 40]
            if any(token in snippet for token in ALLOWLIST_SNIPPETS):
                continue
            violations.append(f"{path.name}: {match.group(0)}")
    assert not violations, "Hard-coded metrics in frontend:\n" + "\n".join(violations)
