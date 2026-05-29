from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_api_base: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    vision_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    chroma_persist_dir: str = "./data/chroma"
    documents_dir: str = "./data/documents"
    upload_dir: str = "./data/uploads"

    wecom_bot_id: str = ""
    wecom_bot_secret: str = ""
    wecom_allow_from: str = ""

    mcp_report_server_path: str = "./mcp_servers/report_server/server.py"
    # Docker: http://mcp-report:8000/mcp | Local dev: leave empty to use stdio subprocess
    mcp_report_url: str = ""
    log_level: str = "INFO"

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def mcp_report_server_abs(self) -> Path:
        p = Path(self.mcp_report_server_path)
        return p if p.is_absolute() else self.project_root / p

    @property
    def allowed_users(self) -> set[str]:
        if not self.wecom_allow_from.strip():
            return set()
        return {u.strip() for u in self.wecom_allow_from.split(",") if u.strip()}


settings = Settings()
