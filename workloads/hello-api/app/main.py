from fastapi import FastAPI

app = FastAPI(
    title="Kaviont Hello API",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)


@app.get("/", tags=["service"])
def root() -> dict[str, str]:
    return {"service": "hello-api", "status": "running", "version": "0.1.0"}


@app.get("/healthz", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", tags=["health"])
def readiness() -> dict[str, str]:
    return {"status": "ready"}
