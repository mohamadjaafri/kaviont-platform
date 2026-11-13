from fastapi import FastAPI

from app.observability import configure_observability


def test_observability_is_disabled_without_otlp_endpoint(monkeypatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    app = FastAPI()

    assert configure_observability(app) is False
    assert not app.user_middleware
