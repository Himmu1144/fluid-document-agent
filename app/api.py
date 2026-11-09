"""The HTTP layer: thin on purpose. It validates input, calls the agent, and turns failures into clear errors."""
import logging
import re

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import ValidationError

from app import agent, config
from app.llm import LLMError
from app.models import AgentRequest, AgentResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
for noisy in ("httpx", "google_genai.models"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

app = FastAPI(
    title="Document Agent",
    description="An autonomous agent that plans its own tasks, runs them with tools, reviews its own draft, "
                "and returns a Word document, from a plain-English request.",
    version="1.0.0",
)

EXAMPLES = {
    "standard": {"summary": "Standard: meeting minutes",
                 "value": {"request": "Write meeting minutes for our weekly KYC onboarding sync."}},
    "complex": {"summary": "Complex: ambiguous, conflicting, missing details",
                "value": {"request": "Proposal for a voice bot for our insurance claims line: launch in 2 weeks, "
                                     "budget under 5 lakh rupees, must support 6 languages, details to follow."}},
}
DOC_ID = re.compile(r"^[0-9a-f]{12}$")
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@app.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    return RedirectResponse("/docs")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/agent", response_model=AgentResponse, responses={
    422: {"description": "The request is missing, too short or too long, or isn't asking for a document"},
    502: {"description": "The model kept returning output that doesn't fit the expected format"},
    503: {"description": "No language model is available right now (all free tiers busy or down)"},
})
def run_agent(http: Request, body: AgentRequest = Body(openapi_examples=EXAMPLES)) -> AgentResponse:
    """Plan → execute with tools → self-check → Word document. Returns the task list, assumptions,
    conflicts, the self-check with before/after for each fix, and a link to download the document."""
    try:
        result = agent.run(body.request)
    except agent.NotADocumentRequest as exc:
        raise HTTPException(422, f"Not a document request: {exc}") from exc
    except LLMError as exc:
        raise HTTPException(503, "No language model is available right now; please try again in a minute.") from exc
    except ValidationError as exc:
        raise HTTPException(502, "The model returned an invalid plan twice in a row; please try again.") from exc
    result.document_url = str(http.base_url).rstrip("/") + result.document_url
    return result


@app.get("/documents/{doc_id}", response_class=FileResponse, responses={404: {"description": "No such document"}})
def download(doc_id: str) -> FileResponse:
    """Download a generated Word document."""
    if not DOC_ID.match(doc_id):  # only ids we generate: no paths, no "../"
        raise HTTPException(404, "No such document")
    matches = sorted(config.OUTPUT_DIR.glob(f"*{doc_id}.docx"))
    if not matches:
        raise HTTPException(404, "No such document")
    return FileResponse(matches[0], media_type=DOCX, filename=matches[0].name)
