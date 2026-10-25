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

from avocat_expert.contracts.common import ClaimKind, SourceReference, SupportStatus, Verdict
from avocat_expert.contracts.services import AnswerRequest, SourcedAnswer, SourcedStatement
from avocat_expert.search.service import HybridSearchService
from avocat_expert.verification.lexverif import CitationVerifier

DISCLAIMER = (
    "Vous utilisez un système d'intelligence artificielle. Résultat produit automatiquement à partir du "
    "corpus officiel ingéré, sans génération de texte. "
    "Il ne constitue pas une consultation juridique et doit être apprécié par un professionnel du droit."
)

_SUPPORT_BY_VERDICT = {
    Verdict.CONFORME: SupportStatus.FONDEE,
    Verdict.INCERTAIN: SupportStatus.INCERTAINE,
    Verdict.NON_CONFORME: SupportStatus.BLOQUEE,
}


def _describe(ref: SourceReference) -> str:
    article = f"article {ref.provision_number}" if ref.provision_number else "article non numéroté"
    if ref.dates_unknown:
        period = "dates d'application non renseignées par la source"
    else:
        start = (
            f"applicable à compter du {ref.valid_from.isoformat()}"
            if ref.valid_from
            else "entrée en vigueur à une date non encore fixée par la source"
        )
        if ref.valid_to:
            end = f"jusqu'au {ref.valid_to.isoformat()} (exclu)"
        elif ref.end_undetermined:
            end = "jusqu'à une date d'abrogation non encore fixée par la source"
        else:
            end = "sans date de fin connue"
        period = f"{start}, {end}"
    return f"{ref.document_title}, {article} — version {ref.official_id}, {period}."


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
                    text=_describe(ref),
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
            semantic_only = sum(
                1
                for hit, statement in zip(hits, statements, strict=True)
                if statement.support is not SupportStatus.BLOQUEE and hit.matched_by == ["semantique"]
            )
            matched = (
                "correspondent aux termes de la question"
                if not semantic_only
                else "ont été retrouvées par les termes de la question ou par proximité de sens "
                f"({semantic_only} par proximité de sens seulement)"
            )
            summary = (
                f"{len(usable)} disposition(s) du corpus officiel, en vigueur au {as_of.isoformat()}, "
                f"{matched}. Les extraits sont cités littéralement ; "
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
