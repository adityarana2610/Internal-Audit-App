import os
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator

class Settings(BaseSettings):
    supabase_db_url: str = Field(..., validation_alias="SUPABASE_DB_URL", description="Direct Postgres connection string")
    supabase_project_ref: str = Field(default="", validation_alias="SUPABASE_PROJECT_REF", description="Supabase project ref")
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    api_auth_token: str = Field(default="", validation_alias="API_AUTH_TOKEN", description="Secret bearer token protecting all audit & policy operations.")
    ai_provider: str = Field(default="gemini", validation_alias="AI_PROVIDER")
    ollama_base_url: str = Field(default="http://localhost:11434", validation_alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="phi4-mini", validation_alias="OLLAMA_MODEL")
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-1.5-flash", validation_alias="GEMINI_MODEL")

    # Qdrant vector database (local Docker)
    qdrant_host: str = Field(default="localhost", validation_alias="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, validation_alias="QDRANT_PORT")
    qdrant_collection: str = Field(default="policy_clauses", validation_alias="QDRANT_COLLECTION")

    # Jina AI embeddings
    jina_api_key: str = Field(default="", validation_alias="JINA_API_KEY")
    jina_embedding_model: str = Field(default="jina-embeddings-v3", validation_alias="JINA_EMBEDDING_MODEL")
    jina_embedding_dimensions: int = Field(default=1024, validation_alias="JINA_EMBEDDING_DIMENSIONS")

    @field_validator("supabase_db_url")
    @classmethod
    def validate_db_url(cls, v):
        if not v or v.startswith("postgresql+psycopg://postgres:[YOUR") or "[YOUR-PASSWORD]" in v:
            raise ValueError("SUPABASE_DB_URL must be set to a real connection string")
        return v

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }

# Create a singleton settings instance
settings = Settings()
