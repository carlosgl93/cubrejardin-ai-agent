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


class ExchangeCodeResponse(BaseModel):
    tenant_id: str
    waba_id: str
    phone_number_id: str
    status: str


@router.post("/exchange", response_model=ExchangeCodeResponse)
async def exchange_facebook_code(
    body: ExchangeCodeRequest,
    ctx: TenantContext = Depends(get_tenant_context),
) -> ExchangeCodeResponse:
    """Exchange a Facebook auth code for a WhatsApp Business access token."""
    creds = await exchange_facebook_code_to_credentials(
        code=body.auth_code,
        tenant_id=ctx.tenant_id,
        waba_id=body.waba_id,
        phone_number_id=body.phone_number_id,
    )
    return ExchangeCodeResponse(
        tenant_id=ctx.tenant_id,
        waba_id=creds["waba_id"],
        phone_number_id=creds["phone_number_id"],
        status=creds["status"],
    )