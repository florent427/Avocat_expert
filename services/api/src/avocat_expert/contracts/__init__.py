"""Contrats structurés et validés échangés entre services et agents.

Chaque contrat est un modèle Pydantic strict (``extra="forbid"``) et versionné.
Les schémas JSON sont exportés dans ``packages/contracts/schemas`` par
``scripts/export_schemas.py`` ; un test vérifie qu'ils sont à jour.
"""

CONTRACTS_VERSION = "1.0.0"
