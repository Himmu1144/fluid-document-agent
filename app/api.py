"""The HTTP layer: thin on purpose. It validates input, calls the agent, and returns its result."""
from fastapi import FastAPI

app = FastAPI(
    title="Document Agent",
    description="An autonomous agent that plans its own tasks and writes a Word document from a plain-English request.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
