# OAuth Implementation Guide (Optional)

## When You Need OAuth

Implement OAuth if you want:
- Multiple businesses to connect their WhatsApp numbers to your platform
- A self-service onboarding flow
- Users to manage their own WhatsApp Business connections

## Current vs OAuth Architecture

### Current (Server-to-Server)
```
Business Owner → Meta Business Manager → Generate Token → Configure in .env
                                                         ↓
                                              Single WhatsApp Bot Instance
```

### With OAuth (Multi-Tenant)
```
Business Owner → Your Platform → Login with Facebook → Grant Permissions
                                                      ↓
                                           Store Token per Business
                                                      ↓
                                        Multiple WhatsApp Bot Instances
```

---

## Implementation Steps

### 1. Create OAuth Endpoints

Add to `api/oauth.py`:

```python
"""OAuth authentication flow for Facebook Login."""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse
import httpx
from config import settings
from models.database import BusinessAccount, SessionLocal
from utils import logger

router = APIRouter(prefix="/auth", tags=["authentication"])

# Add to settings.py:
# facebook_app_id: str = Field(..., validation_alias="FACEBOOK_APP_ID")
# facebook_app_secret: str = Field(..., validation_alias="FACEBOOK_APP_SECRET")
# oauth_redirect_uri: str = Field(..., validation_alias="OAUTH_REDIRECT_URI")
# frontend_url: str = Field("http://localhost:3000", validation_alias="FRONTEND_URL")

@router.get("/facebook/login")
async def facebook_login():
    """Redirect user to Facebook OAuth dialog."""
    
    # Document this URL in your screencast!
    facebook_oauth_url = (
        f"https://www.facebook.com/v21.0/dialog/oauth?"
        f"client_id={settings.facebook_app_id}"
        f"&redirect_uri={settings.oauth_redirect_uri}"
        f"&state={_generate_csrf_token()}"
        f"&scope=whatsapp_business_management,whatsapp_business_messaging"
    )
    
    logger.info("oauth_redirect", url=facebook_oauth_url)
    return RedirectResponse(url=facebook_oauth_url)


@router.get("/facebook/callback")
async def facebook_callback(
    code: str = Query(...),
    state: str = Query(...)
):
    """Handle Facebook OAuth callback."""
    
    # Validate CSRF token
    if not _validate_csrf_token(state):
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    
    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        token_response = await client.get(
            "https://graph.facebook.com/v21.0/oauth/access_token",
            params={
                "client_id": settings.facebook_app_id,
                "client_secret": settings.facebook_app_secret,
                "redirect_uri": settings.oauth_redirect_uri,
                "code": code,
            }
        )
        
        if token_response.status_code != 200:
            logger.error("token_exchange_failed", response=token_response.text)
            raise HTTPException(status_code=400, detail="Failed to exchange code")
        
        token_data = token_response.json()
        access_token = token_data["access_token"]
        
        # Get business account info
        business_info = await _get_business_info(access_token)
        
        # Store in database
        db = SessionLocal()
        try:
            business = BusinessAccount(
                facebook_user_id=business_info["id"],
                business_name=business_info.get("name", "Unknown"),
                access_token=access_token,
                whatsapp_phone_number_id=business_info.get("phone_number_id"),
            )
            db.add(business)
            db.commit()
            
            logger.info(
                "business_connected",
                business_id=business.id,
                facebook_user_id=business_info["id"]
            )
            
        finally:
            db.close()
    
    # Redirect to success page
    return RedirectResponse(
        url=f"{settings.frontend_url}/auth/success?business_id={business.id}"
    )


async def _get_business_info(access_token: str) -> dict:
    """Fetch WhatsApp Business Account info."""
    async with httpx.AsyncClient() as client:
        # Get user's WhatsApp Business Accounts
        response = await client.get(
            "https://graph.facebook.com/v21.0/me/businesses",
            params={"access_token": access_token}
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch business info")
        
        data = response.json()
        # Return first business (adapt as needed)
        return data.get("data", [{}])[0]


def _generate_csrf_token() -> str:
    """Generate CSRF token for OAuth state parameter."""
    import secrets
    return secrets.token_urlsafe(32)


def _validate_csrf_token(state: str) -> bool:
    """Validate CSRF token (implement proper storage/validation)."""
    # TODO: Store in Redis/session and validate
    return True  # Simplified for demo
```

### 2. Add Database Model

Add to `models/database.py`:

```python
class BusinessAccount(Base):
    """Stores OAuth tokens for each connected business."""
    
    __tablename__ = "business_accounts"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    facebook_user_id = Column(String, unique=True, nullable=False)
    business_name = Column(String)
    access_token = Column(String, nullable=False)  # Encrypt in production!
    whatsapp_phone_number_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
```

### 3. Create Simple Frontend

Add `oauth_demo.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Connect WhatsApp Business - CubreJardin Bot</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 600px;
            margin: 100px auto;
            padding: 20px;
            text-align: center;
        }
        .card {
            background: white;
            border-radius: 12px;
            padding: 40px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.1);
        }
        h1 {
            color: #1877f2;
            margin-bottom: 20px;
        }
        .connect-btn {
            background: #1877f2;
            color: white;
            border: none;
            padding: 15px 40px;
            font-size: 16px;
            border-radius: 8px;
            cursor: pointer;
            margin-top: 20px;
            text-decoration: none;
            display: inline-block;
        }
        .connect-btn:hover {
            background: #166fe5;
        }
        .info {
            color: #666;
            font-size: 14px;
            margin-top: 20px;
        }
        .permission-list {
            text-align: left;
            margin: 20px auto;
            max-width: 400px;
        }
        .permission-item {
            padding: 10px;
            border-left: 3px solid #1877f2;
            margin: 10px 0;
            background: #f7f7f7;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>🌱 Connect Your WhatsApp Business</h1>
        <p>Connect your WhatsApp Business account to enable AI-powered customer support for CubreJardin.</p>
        
        <div class="permission-list">
            <div class="permission-item">
                <strong>Send Messages</strong><br>
                <small>Respond to customer inquiries automatically</small>
            </div>
            <div class="permission-item">
                <strong>Receive Messages</strong><br>
                <small>Get notified of incoming messages via webhook</small>
            </div>
            <div class="permission-item">
                <strong>Manage Business Account</strong><br>
                <small>Access your WhatsApp Business settings</small>
            </div>
        </div>
        
        <a href="/auth/facebook/login" class="connect-btn">
            Login with Facebook
        </a>
        
        <div class="info">
            You'll be redirected to Facebook to grant permissions.<br>
            Your data is secure and will only be used for WhatsApp messaging.
        </div>
    </div>
    
    <script>
        // Check for success redirect
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('business_id')) {
            document.querySelector('.card').innerHTML = `
                <h1>✅ Successfully Connected!</h1>
                <p>Your WhatsApp Business account is now connected.</p>
                <p>Business ID: ${urlParams.get('business_id')}</p>
            `;
        }
    </script>
</body>
</html>
```

### 4. Serve the Frontend

Add to `main.py`:

```python
from fastapi.responses import HTMLResponse
from pathlib import Path

@app.get("/connect", response_class=HTMLResponse)
async def connect_page():
    """Serve OAuth connection page."""
    html_file = Path("oauth_demo.html")
    if html_file.exists():
        return html_file.read_text()
    return "<h1>OAuth page not found</h1>"
```

### 5. Update Environment Variables

Add to `.env`:

```bash
# OAuth Configuration (if implementing OAuth flow)
FACEBOOK_APP_ID=your_app_id_here
FACEBOOK_APP_SECRET=your_app_secret_here
OAUTH_REDIRECT_URI=https://your-domain.com/auth/facebook/callback
FRONTEND_URL=http://localhost:3000
```

---

## Screencast Script with OAuth

If you implement OAuth, your screencast should show:

### Part 1: User Journey (5 min)
1. **Landing Page**: Show http://localhost:8000/connect
   - Caption: "Business owner visits connection page"
   
2. **Click "Login with Facebook"**
   - Caption: "User initiates Facebook login"
   
3. **Facebook OAuth Dialog**
   - Shows permissions being requested
   - Caption: "Facebook prompts user to grant whatsapp_business_management permission"
   
4. **User Grants Permission**
   - Click "Continue" or "Allow"
   - Caption: "User explicitly grants permissions to the app"
   
5. **Success Page**
   - Shows "Successfully Connected"
   - Caption: "OAuth flow complete - token stored securely"

### Part 2: Behind the Scenes (3 min)
6. **Show Code**: OAuth endpoint in api/oauth.py
   - Caption: "Backend exchanges authorization code for access token"
   
7. **Show Database**: BusinessAccount table
   - Caption: "Token stored per business account"
   
8. **End-to-End**: Send test message
   - Caption: "Bot uses stored token to send/receive messages"

---

## Testing OAuth Locally

```bash
# 1. Update .env with OAuth credentials
FACEBOOK_APP_ID=123456789
FACEBOOK_APP_SECRET=abc123def456
OAUTH_REDIRECT_URI=http://localhost:8000/auth/facebook/callback

# 2. Start the server
uvicorn main:app --reload

# 3. Expose with ngrok (Facebook needs HTTPS)
ngrok http 8000

# 4. Update redirect URI in Facebook App settings
# Dashboard → App Settings → Basic → Add Platform → Website
# OAuth Redirect URIs: https://YOUR-NGROK-URL.ngrok.io/auth/facebook/callback

# 5. Visit connection page
open http://localhost:8000/connect
```

---

## Database Migration

```sql
-- Add business_accounts table
CREATE TABLE business_accounts (
    id VARCHAR PRIMARY KEY,
    facebook_user_id VARCHAR UNIQUE NOT NULL,
    business_name VARCHAR,
    access_token VARCHAR NOT NULL,
    whatsapp_phone_number_id VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Add business_id to conversations
ALTER TABLE conversation 
ADD COLUMN business_id VARCHAR REFERENCES business_accounts(id);
```

---

## Security Considerations

1. **Encrypt Tokens**: Use Fernet or AWS KMS to encrypt `access_token` in database
2. **HTTPS Only**: Never use HTTP in production for OAuth
3. **CSRF Protection**: Properly validate `state` parameter (use Redis)
4. **Token Refresh**: Implement token refresh if using short-lived tokens
5. **Scope Validation**: Verify granted scopes match requested scopes

---

## Recommendation

**For your current use case** (single business bot), stick with **server-to-server auth** and clearly document it in your submission. Only implement OAuth if you plan to offer multi-tenant platform service.

