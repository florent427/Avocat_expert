"""Adaptateur vers le moteur déterministe Rust ``lexverif`` (contrat JSON v2).

Le moteur est invoqué en sous-processus, sans shell, avec délai maximal.
Toute erreur du moteur est remontée : une vérification qui n'a pas pu avoir
lieu n'est jamais présentée comme réussie.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from typing import Any

from avocat_expert.contracts.common import CheckOutcome, Verdict
from avocat_expert.contracts.services import CitationCheck, CitationVerification
from avocat_expert.storage.corpus import CorpusRepository, VersionRecord

CONTRACT_VERSION = "2"


class VerificationUnavailable(RuntimeError):
    """Le moteur de vérification n'a pas pu produire de résultat."""


def _period(v: VersionRecord) -> dict[str, Any]:
    return {
        "official_id": v.official_id,
        "valid_from": v.valid_from.isoformat() if v.valid_from else None,
        "valid_to": v.valid_to.isoformat() if v.valid_to else None,
        "end_undetermined": v.end_undetermined,
        "status_raw": v.source_status,
    }


class LexverifEngine:
    def __init__(self, binary: str, timeout_s: float = 5.0) -> None:
        resolved = shutil.which(binary)
        if resolved is None:
            raise VerificationUnavailable(f"binaire lexverif introuvable : {binary}")
        self._binary = resolved
        self._timeout = timeout_s

    def call(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = json.dumps({"contract_version": CONTRACT_VERSION, "command": command, "payload": payload})
        try:
            completed = subprocess.run(  # noqa: S603 — binaire résolu, arguments fixes, pas de shell
                [self._binary],
                input=request.encode("utf-8"),
                capture_output=True,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise VerificationUnavailable("délai dépassé pour lexverif") from exc
        try:
            response: dict[str, Any] = json.loads(completed.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VerificationUnavailable("réponse illisible de lexverif") from exc
        if response.get("status") != "ok" or completed.returncode != 0:
            raise VerificationUnavailable(f"erreur lexverif : {response.get('error', 'inconnue')}")
        return response


class CitationVerifier:
    """Assemble les données du corpus et délègue les contrôles au moteur Rust."""

    def __init__(self, repository: CorpusRepository, engine: LexverifEngine) -> None:
        self._repository = repository
        self._engine = engine

    def verify(self, official_id: str, quote: str, as_of: date, territory: str | None) -> CitationVerification:
        candidate = self._repository.get_current_version(official_id)
        siblings = self._repository.versions_of_provision(candidate.provision_id) if candidate else []
        knowledge = self._repository.knowledge_date(candidate.reference.source_code) if candidate else None
        payload: dict[str, Any] = {
            "citation": {
                "official_id": official_id,
                "quote": quote,
                "as_of": as_of.isoformat(),
                "territory": territory,
            },
            "candidate": None
            if candidate is None
            else {
                "official_id": candidate.official_id,
                "text": candidate.text_content,
                "period": _period(candidate),
                "territorial_scope": candidate.territorial_scope,
            },
            "sibling_versions": [_period(v) for v in siblings],
            "knowledge_date": None if knowledge is None else knowledge.isoformat(),
        }
        response = self._engine.call("verify_citation", payload)
        result = response["result"]
        span = result.get("quote_span") or {}
        resolution = result.get("resolution_at_date") or {}
        start, end = span.get("start"), span.get("end")
        if candidate is not None and start is not None and end is not None:
            # Le moteur renvoie des positions en octets UTF-8 ; le contrat expose des caractères.
            raw = candidate.text_content.encode("utf-8")
            start, end = len(raw[:start].decode("utf-8")), len(raw[:end].decode("utf-8"))
        return CitationVerification(
            official_id=official_id,
            verdict=Verdict(result["verdict"]),
            checks=[
                CitationCheck(check=c["check"], outcome=CheckOutcome(c["outcome"]), detail=c["detail"])
                for c in result["checks"]
            ],
            uncertainties=list(result["uncertainties"]),
            quote_start=start,
            quote_end=end,
            version_in_force_at_date=resolution.get("official_id"),
            engine_version=response["engine_version"],
            contract_version=response["contract_version"],
        )
