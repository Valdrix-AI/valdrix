
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any
from app.shared.lead_gen.assessment import FreeAssessmentService
from app.shared.core.rate_limit import rate_limit

router = APIRouter()
assessment_service = FreeAssessmentService()

@router.get("/csrf")
async def get_csrf_token(request: Request):
    """
    Get a CSRF token to be used in subsequent POST/PUT/DELETE requests.
    Sets the fast-csrf-token cookie and returns the token in the body.
    """
    from fastapi_csrf_protect import CsrfProtect
    csrf = CsrfProtect()
    token = csrf.generate_csrf(getattr(request.state, "request_id", "anonymous"))
    response = JSONResponse(content={"csrf_token": token})
    csrf.set_csrf_cookie(token, response)
    return response

@router.post("/assessment")
@rate_limit("5/day")
async def run_public_assessment(_request: Request, body: Dict[str, Any]):
    """
    Public endpoint for lead-gen cost assessment.
    Limited to 5 requests per day per IP to prevent abuse.
    """
    try:
        result = await assessment_service.run_assessment(body)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        # Don't leak internals for public endpoints
        raise HTTPException(status_code=500, detail="An unexpected error occurred during assessment")
