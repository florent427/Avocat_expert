# ADR 0015 — Observabilité à liste blanche

**Statut** : proposée — implémentée · 2026-10-24

## Contexte
L'instrumentation automatique OpenTelemetry enregistre URL, en-têtes et
parfois corps de requêtes. Constat du 2026-10-24 : FastAPI émet lui-même des
spans (attribut `code.function.name`), hors de tout contrôle applicatif.

## Décision
* Aucune instrumentation automatique. Spans explicites : `http.request`
  (méthode, gabarit de route, statut) et spans métier (statut, compteurs).
* `ALLOWED_ATTRIBUTES` : seuls ces attributs scalaires sont acceptés à la
  création **et** à l'export : `AllowlistSpanExporter` filtre tout span, y
  compris ceux de bibliothèques tierces, et supprime événements (messages
  d'exception) et descriptions de statut.
* Tests : aucune donnée d'une question (nom, faits) dans les spans exportés,
  y compris si elle figure dans l'URL.
* Export OTLP/HTTP activé par `AVX_OTEL_EXPORTER_ENDPOINT` ; collecteur
  (ADOT/CloudWatch ou autre) à choisir au déploiement.
