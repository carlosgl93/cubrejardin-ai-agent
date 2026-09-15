"""Facebook / Meta OAuth code exchange endpoint.

Flow:
  1. Frontend completes FB Embedded Signup and receives a short-lived auth code.
  2. Frontend POSTs the code here with its Supabase JWT.
  3. This endpoint delegates to ``services.facebook_auth.exchange_facebook_code_to_credentials``
     to exchange the code, resolve WABA + phone, and persist credentials.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.tenant_context import TenantContext, get_tenant_context
from services.facebook_auth import exchange_facebook_code_to_credentials
from pydantic import BaseModel

router = APIRouter()


class ExchangeCodeRequest(BaseModel):
    auth_code: str
    waba_id: str = ""
    phone_number_id: str = ""
    page_id: str = ""
    ig_user_id: str = ""


class ExchangeCodeResponse(BaseModel):
    tenant_id: str
    waba_id: str
    phone_number_id: str
    status: str
    instagram_connected: bool = False
    page_id: str = ""
    ig_user_id: str = ""


@router.post("/exchange", response_model=ExchangeCodeResponse)
async def exchange_facebook_code(
    body: ExchangeCodeRequest,
    ctx: TenantContext = Depends(get_tenant_context),
) -> ExchangeCodeResponse:
    """Exchange a Facebook auth code for WA + IG credentials.

    Single popup collects permissions for both channels; backend persists
    whichever it can resolve. If IG scopes aren't granted, ``instagram_connected``
    comes back false and the IG card in OnboardingWizard stays disconnected
    so the customer can retry with IG scopes enabled.
    """
    creds = await exchange_facebook_code_to_credentials(
        code=body.auth_code,
        tenant_id=ctx.tenant_id,
        waba_id=body.waba_id,
        phone_number_id=body.phone_number_id,
        page_id=body.page_id,
        ig_user_id=body.ig_user_id,
    )
    return ExchangeCodeResponse(
        tenant_id=ctx.tenant_id,
        waba_id=creds["waba_id"],
        phone_number_id=creds["phone_number_id"],
        status=creds["status"],
        instagram_connected=creds.get("instagram_connected", False),
        page_id=creds.get("page_id", ""),
        ig_user_id=creds.get("ig_user_id", ""),
    )