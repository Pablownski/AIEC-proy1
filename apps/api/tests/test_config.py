from app.core.config import Settings


def test_cors_origins_list_splits_and_trims_comma_separated_values():
    settings = Settings(cors_origins=" http://a.com, http://b.com ,")

    assert settings.cors_origins_list == ["http://a.com", "http://b.com"]


def test_default_app_env_is_development():
    settings = Settings()

    assert settings.app_env == "development"


def test_groq_defaults_allow_mock_without_credentials():
    settings = Settings()
    assert settings.groq_api_key is None
    assert settings.groq_model == "openai/gpt-oss-120b"


def test_groq_environment_and_secret_redaction(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "custom-model")
    settings = Settings()
    assert settings.groq_model == "custom-model"
    assert settings.groq_api_key.get_secret_value() == "test-key"
    assert "test-key" not in repr(settings)
    assert "test-key" not in settings.model_dump_json()
