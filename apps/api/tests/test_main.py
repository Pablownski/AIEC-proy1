from fastapi import FastAPI

from app.main import app


def test_app_is_a_fastapi_instance():
    assert isinstance(app, FastAPI)


def test_app_has_the_expected_title():
    assert app.title == "AGIChat API"
