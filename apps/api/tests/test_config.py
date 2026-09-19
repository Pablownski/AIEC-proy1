from app.core.config import Settings


def test_cors_origins_list_splits_and_trims_comma_separated_values():
    settings = Settings(cors_origins=" http://a.com, http://b.com ,")

    assert settings.cors_origins_list == ["http://a.com", "http://b.com"]


def test_default_app_env_is_development():
    settings = Settings()

    assert settings.app_env == "development"
