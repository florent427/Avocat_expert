"""Connecteur DILA LEGI — dumps XML open data (https://echanges.dila.gouv.fr/OPENDATA/LEGI/).

Le format a été vérifié sur l'archive réelle ``LEGI_20261023-215041.tar.gz``
(voir ``docs/sources/verification-documentation-officielle.md``). Toute
évolution du format doit faire l'objet d'une nouvelle version du connecteur.
"""

CONNECTOR_VERSION = "dila-legi-xml/0.1.0"
SOURCE_CODE = "DILA_LEGI"
