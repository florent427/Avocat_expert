"""Réponse sourcée en mode extractif.

Aucun texte juridique n'est généré : la réponse est composée d'extraits
littéraux de versions officielles, chacun soumis au moteur de vérification.
Une citation non conforme est bloquée (son extrait n'est pas restitué comme
fondement). La pertinence juridique des extraits n'est pas évaluée par ce
mode et l'utilisateur en est explicitement informé.
"""

from __future__ import annotations

import hashlib
from datetime import date

from avocat_expert.contracts.common import ClaimKind, SupportStatus, Verdict
from avocat_expert.contracts.services import AnswerRequest, SourcedAnswer, SourcedStatement
from avocat_expert.search.service import HybridSearchService
from avocat_expert.verification.lexverif import CitationVerifier

DISCLAIMER = (
    "Résultat produit automatiquement à partir du corpus officiel ingéré, sans génération de texte. "
    "Il ne constitue pas une consultation juridique et doit être apprécié par un professionnel du droit."
)

_SUPPORT_BY_VERDICT = {
    Verdict.CONFORME: SupportStatus.FONDEE,
    Verdict.INCERTAIN: SupportStatus.INCERTAINE,
    Verdict.NON_CONFORME: SupportStatus.BLOQUEE,
}


def _describe(title: str, number: str, official_id: str, valid_from: date, valid_to: date | None) -> str:
    end = f"jusqu'au {valid_to.isoformat()} (exclu)" if valid_to else "sans date de fin connue"
    return (
        f"{title}, article {number} — version {official_id}, applicable à compter du {valid_from.isoformat()}, {end}."
    )


class ExtractiveAnswerService:
    mode = "EXTRACTIF"

    def __init__(self, search: HybridSearchService, verifier: CitationVerifier) -> None:
        self._search = search
        self._verifier = verifier

    def answer(self, request: AnswerRequest, today: date) -> SourcedAnswer:
        as_of = request.as_of or today
        outcome = self._search.search(request.question, as_of, request.max_sources)
        search_response = outcome.response
        uncertainties = list(outcome.notes)
        statements: list[SourcedStatement] = []
        # Une question visant une disposition précise introuvable ne reçoit pas
        # en guise de réponse d'autres dispositions (risque de confusion).
        explicit_unresolved = outcome.explicit_requested > 0 and outcome.explicit_resolved == 0
        hits = [] if explicit_unresolved else search_response.hits

        for hit in hits:
            ref = hit.reference
            verification = self._verifier.verify(ref.official_id, hit.excerpt, as_of, request.territory)
            support = _SUPPORT_BY_VERDICT[verification.verdict]
            statements.append(
                SourcedStatement(
                    kind=ClaimKind.DROIT_APPLICABLE,
                    text=_describe(
                        ref.document_title, ref.provision_number, ref.official_id, ref.valid_from, ref.valid_to
                    ),
                    citation=ref,
                    quote=None if support is SupportStatus.BLOQUEE else hit.excerpt,
                    verification=verification,
                    support=support,
                )
            )
            uncertainties.extend(
                f"{ref.provision_number} : {u}" for u in verification.uncertainties if u not in uncertainties
            )

        usable = [s for s in statements if s.support is not SupportStatus.BLOQUEE]
        if explicit_unresolved:
            status = SupportStatus.BLOQUEE
            summary = (
                "La ou les dispositions visées par la question sont introuvables dans le corpus ingéré à la date "
                "indiquée. Aucune autre disposition n'est proposée à leur place."
            )
        elif not usable:
            status = SupportStatus.BLOQUEE
            summary = (
                "Aucune disposition du corpus ingéré n'a pu être citée de manière vérifiable pour cette "
                "question à la date indiquée. Aucune réponse n'est proposée."
            )
        else:
            status = (
                SupportStatus.FONDEE
                if all(s.support is SupportStatus.FONDEE for s in usable)
                else SupportStatus.INCERTAINE
            )
            summary = (
                f"{len(usable)} disposition(s) du corpus officiel, en vigueur au {as_of.isoformat()}, "
                "correspondent aux termes de la question. Les extraits sont cités littéralement ; "
                "leur pertinence et leur portée juridiques ne sont pas évaluées automatiquement."
            )
        if usable:
            uncertainties.append("pertinence juridique des extraits non évaluée (mode extractif)")

        return SourcedAnswer(
            question_sha256=hashlib.sha256(request.question.encode("utf-8")).hexdigest(),
            as_of=as_of,
            mode=self.mode,
            status=status,
            summary=summary,
            statements=statements,
            uncertainties=list(dict.fromkeys(uncertainties)),
            disclaimer=DISCLAIMER,
            search=search_response,
        )
