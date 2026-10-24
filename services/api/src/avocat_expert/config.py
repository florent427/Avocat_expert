"""Configuration par variables d'environnement (préfixe ``AVX_``).

Aucun secret n'a de valeur par défaut. En environnement ``production``, le
mode d'authentification de développement est refusé au démarrage.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AVX_", extra="ignore")

    environment: Literal["local", "test", "staging", "production"] = "local"
    database_url: str = ""
    lexverif_bin: str = "lexverif"
    lexverif_timeout_s: float = 5.0
    auth_mode: Literal["dev_token", "oidc"] = "dev_token"
    #: Empreinte SHA-256 (hex) du jeton de développement ; jamais le jeton en clair.
    dev_token_sha256: str = ""
    oidc_issuer: str = ""
    oidc_audience: str = ""

    @model_validator(mode="after")
    def _guard_production(self) -> Settings:
        if self.environment in ("staging", "production") and self.auth_mode == "dev_token":
            raise ValueError("le mode d'authentification dev_token est interdit hors environnement local/test")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
