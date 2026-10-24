"""Exporte les schémas JSON des contrats vers packages/contracts/schemas.

Usage : ``uv run python scripts/export_schemas.py [--check]``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from avocat_expert.contracts import agents, services

OUT = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "schemas"

MODELS = {
    "SearchRequest": services.SearchRequest,
    "SearchResponse": services.SearchResponse,
    "AnswerRequest": services.AnswerRequest,
    "SourcedAnswer": services.SourcedAnswer,
    "CitationVerificationRequest": services.CitationVerificationRequest,
    "CitationVerification": services.CitationVerification,
    "AgentTask": agents.AgentTask,
    "AgentResult": agents.AgentResult,
    "RoutingDecision": agents.RoutingDecision,
}


def render() -> dict[str, str]:
    return {
        f"{name}.schema.json": json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False, sort_keys=True)
        + "\n"
        for name, model in MODELS.items()
    }


def main() -> int:
    check = "--check" in sys.argv
    rendered = render()
    stale = [n for n, c in rendered.items() if not (OUT / n).exists() or (OUT / n).read_text("utf-8") != c]
    if check:
        if stale:
            print("schémas obsolètes : " + ", ".join(stale), file=sys.stderr)
            return 1
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for name, content in rendered.items():
        (OUT / name).write_text(content, "utf-8")
    print(f"{len(rendered)} schémas écrits dans {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
