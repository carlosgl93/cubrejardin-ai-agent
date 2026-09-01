# Facebook App Review Guide - WhatsApp Business Management Permission

## Current Setup Analysis

Your app uses a **server-to-server authentication model** with a permanent Page Access Token, not a user-facing OAuth flow. This is common for single-business WhatsApp bots.

## Two Submission Options

### Option 1: Server-to-Server Submission (Recommended for your use case)

Since you're using a page access token and don't have a user-facing login flow, clearly state this in your submission.

#### Submission Notes Template

```
This is a server-to-server application using a Page Access Token with whatsapp_business_management permission.

AUTHENTICATION METHOD:
- No frontend Meta login flow is visible to end users
- The application uses a permanent Page Access Token generated via Meta Business Manager
- Token has whatsapp_business_management permission pre-authorized by the business owner

USE CASE:
This WhatsApp AI Agent automatically responds to customer inquiries for CubreJardin business via WhatsApp Cloud API. The bot:
- Receives incoming WhatsApp messages via webhook
- Processes FAQs using RAG (Retrieval Augmented Generation)
- Sends automated responses to customers
- Escalates complex queries to human agents

PERMISSION USAGE:
The whatsapp_business_management permission is used to:
1. Receive incoming messages from customers (webhook subscription)
2. Send text responses to customer inquiries
3. Send approved message templates outside 24-hour window
4. Mark messages as read
5. Transfer conversation control to human agents (Page Inbox)

TOKEN GENERATION FLOW (shown in screencast):
1. Business owner logs into Meta Business Manager
2. Navigates to WhatsApp Business Account settings
3. Generates System User with whatsapp_business_management permission
4. Creates permanent token assigned to the WhatsApp Business Phone Number
5. Token is configured in the server application environment variables
```

#### What to Show in Screencast

1. **Meta Business Manager Access** (2-3 min)
   - Log into business.facebook.com
   - Navigate to Business Settings → Users → System Users
   - Show existing system user OR create new one
   - Show whatsapp_business_management permission is granted

2. **Token Generation** (2-3 min)
   - Click "Generate New Token"
   - Select your app
   - Check "whatsapp_business_management" permission
   - Show token being generated (blur the actual token)
   - Explain: "This token will be used server-side"

3. **Application Configuration** (1-2 min)
   - Show .env.example file (NOT actual .env with real tokens)
   - Highlight FACEBOOK_PAGE_ACCESS_TOKEN variable
   - Explain: "The generated token is configured here"

4. **End-to-End Use Case** (3-5 min)
   - Show webhook configuration in Meta Dashboard
   - Demonstrate incoming message to WhatsApp number
   - Show webhook receiving the message (server logs)
   - Show bot processing and responding
   - Show message delivered to customer
   - (Optional) Show escalation to human agent

5. **Captions to Include**
   - "Server-to-server app - no user login required"
   - "Business owner grants permissions via Business Manager"
   - "Token configured in server environment"
   - "whatsapp_business_management enables sending/receiving messages"

---

### Option 2: Implement OAuth Flow (If you want multi-tenant support)

If you want to allow multiple businesses to connect their WhatsApp numbers to your platform, you'll need a proper OAuth flow. See `oauth_implementation_guide.md` for details.

---

## Screencast Best Practices

### Technical Requirements
- **Language**: English UI (change Meta interface to English)
- **Resolution**: 1920x1080 minimum
- **Duration**: 5-10 minutes (max 15 minutes)
- **Format**: MP4, MOV, or AVI
- **Audio**: Clear narration in English OR text captions

### Narration Script Template

```
"This is a server-to-server WhatsApp Business API integration for CubreJardin customer support.

[Screen: Meta Business Manager login]
I'm logging into Meta Business Manager as the business owner.

[Screen: System Users]
Here in Business Settings, I navigate to System Users where we manage API access.

[Screen: System User details or create new]
This system user has the whatsapp_business_management permission, which allows our server to send and receive messages through WhatsApp Cloud API.

[Screen: Generate Token or show existing]
We generate a permanent token with the whatsapp_business_management permission selected. This token is configured server-side in our application.

[Screen: Application code/env example]
The token is securely stored in environment variables, not exposed to end users.

[Screen: Webhook configuration]
Our webhook is configured to receive messages from our WhatsApp Business Number.

[Screen: Send test message from phone]
When a customer sends a message to our WhatsApp number...

[Screen: Server receiving webhook]
Our server receives the webhook event with the message content...

[Screen: Bot responding]
The bot processes the inquiry using AI and sends an automated response...

[Screen: Customer receives message]
The customer receives the answer immediately.

This demonstrates the complete flow of the whatsapp_business_management permission usage in our server-to-server application."
```

### What to Blur/Hide
- ❌ Actual access tokens
- ❌ App secrets
- ❌ Phone number IDs (optional, can show)
- ✅ Can show: webhook URLs, public endpoints, demo messages

### Recording Tools
- **macOS**: QuickTime Player (free), ScreenFlow (paid), or OBS Studio (free)
- **Captions**: iMovie (free on Mac), DaVinci Resolve (free), or Camtasia (paid)

---

## Common Rejection Reasons & How to Avoid

| Rejection Reason | Solution |
|-----------------|----------|
| "Doesn't show Meta login flow" | Clearly state "server-to-server" in submission notes |
| "Doesn't show permission grant" | Show System User permissions in Business Manager |
| "Doesn't show end-to-end use case" | Include complete flow: message in → processing → response out |
| "No captions/unclear UI" | Add text overlays explaining each step |
| "Non-English interface" | Change Meta Business Manager language to English |

---

## Checklist Before Submission

- [ ] Submission notes explicitly say "server-to-server app"
- [ ] Submission notes explain no frontend login flow
- [ ] Screencast shows Meta Business Manager access
- [ ] Screencast shows whatsapp_business_management permission
- [ ] Screencast shows token generation or existing token access
- [ ] Screencast demonstrates complete message flow (send → receive → respond)
- [ ] Screencast has English captions/narration
- [ ] All sensitive tokens/secrets are blurred
- [ ] Duration is 5-15 minutes
- [ ] Video quality is clear and readable

---

## Next Steps

1. **Record Screencast**: Follow the script above
2. **Add Captions**: Explain each step clearly
3. **Review**: Watch it yourself - is the flow clear?
4. **Submit**: Upload to Facebook App Review with the submission notes

---

## Need Help?

- Meta Business Manager: https://business.facebook.com/settings
- WhatsApp Cloud API Docs: https://developers.facebook.com/docs/whatsapp/cloud-api
- App Review Guide: https://developers.facebook.com/docs/app-review

---

# Instagram App Review Addendum

For `instagram_business_basic`, `instagram_business_manage_messages`, `instagram_business_manage_comments` permissions on the same `Agents-Whtsapp` app (or a new combined app — see ROADMAP.md).

## Key Differences vs WhatsApp Submission

| Aspect | WhatsApp | Instagram |
|---|---|---|
| Auth model | Server-to-server (permanent token) | **OAuth via Instagram Login** (user-facing flow) |
| Test account | WA Business number | IG **Professional** account (Business or Creator) |
| Permission names | `whatsapp_business_management` | `instagram_business_basic`, `instagram_business_manage_messages`, `instagram_business_manage_comments` |
| Webhook | Single webhook per WABA | Webhooks per IG account subscribed to app |
| Business verification | Pre-verified for SG CLOUD SpA | Pre-verified for SG CLOUD SpA (reuses same Business Manager) |

**Critical:** IG uses **Instagram Login** (OAuth), not server-to-server tokens. The screencast **must** show the user-facing OAuth flow.

## Submission Notes Template

```
This is a multi-tenant chatbot platform that connects to Instagram Professional
accounts via Instagram Login (OAuth 2.0) to automate customer service DMs.

AUTHENTICATION METHOD:
- Instagram Login (OAuth 2.0) flow — end user authorizes the app
- Each tenant (e.g. CubreJardin) connects their IG Professional account via OAuth
- App exchanges short-lived code for long-lived user access token
- Token refresh handled server-side via jobs/refresh_instagram_tokens.py cron

USE CASE:
CubreJardin (and future tenants) uses this platform to automate responses to
customer DMs on Instagram. The bot:
- Receives incoming IG DMs via webhook subscription
- Processes FAQs using RAG (Retrieval Augmented Generation)
- Sends automated responses back through the Instagram Messaging API
- Escalates complex queries to human agents

PERMISSIONS REQUESTED:
1. instagram_business_basic — read basic IG account profile info
2. instagram_business_manage_messages — receive/send DMs on behalf of the account
3. instagram_business_manage_comments — read/reply to comments (optional for v1)

PERMISSION USAGE:
1. Receive incoming DMs from customers (webhook subscription on messages event)
2. Send text responses to customer inquiries via POST /{ig-user-id}/messages
3. Mark conversations as seen
4. Token refresh on long-lived tokens (60-day expiry)

OAUTH FLOW (shown in screencast):
1. Tenant clicks "Connect Instagram" in our backoffice
2. Redirected to Instagram Login OAuth dialog
3. Tenant grants requested permissions
4. IG redirects back to our callback URL with auth code
5. Server exchanges code for short-lived user token
6. Server exchanges short-lived for long-lived token (60 days)
7. Long-lived token stored per tenant in database
8. Cron job refreshes token before expiry
```

## What to Show in Screencast

1. **App Configuration** (2 min)
   - developers.facebook.com → My Apps → `Agents-Whtsapp`
   - Show Instagram product is added
   - Show "Instagram API with Instagram Login" is configured
   - Show valid OAuth redirect URIs listed

2. **Business Manager Verification** (1 min)
   - business.facebook.com/settings
   - Show SG CLOUD SpA is verified
   - Show the app is owned by this Business Manager

3. **OAuth Flow** (3-4 min)
   - Open the backoffice "Connect Instagram" button
   - Redirect to Instagram Login screen
   - Show the permission scopes requested (`instagram_business_basic`, `instagram_business_manage_messages`)
   - Click "Authorize"
   - Show redirect to callback with auth code
   - Show server log: code exchanged for token, token stored

4. **End-to-End Use Case** (3-4 min)
   - From a separate phone/account, send a DM to CubreJardin's IG Professional account
   - Show webhook logs receiving the message event
   - Show bot processing and responding
   - Show the response appearing in the customer's DM
   - Optional: show escalation flow

5. **Token Refresh** (1 min)
   - Show jobs/refresh_instagram_tokens.py running
   - Show log output confirming token refresh succeeded

## Test Account Requirements

When submitting, you must provide:
- **IG Professional account username** that Meta's reviewers can use as test recipient
- **Test instructions** with: exact message to send, expected bot reply
- **Screencast URL** (hosted on YouTube/Drive/Loom with public access)

## Common Rejection Reasons (IG-specific)

| Rejection Reason | Solution |
|---|---|
| "No OAuth flow shown" | Screencast must include the user clicking "Authorize" on Instagram Login |
| "Test account not provided" | Include the IG username in submission form |
| "Permission usage unclear" | Explicitly map each scope to a server endpoint that calls it |
| "Token refresh not shown" | Demonstrate the cron job refreshing tokens |
| "Webhooks not verified" | Show webhook subscription in App Dashboard + live event delivery |

## Checklist Before Submission

- [ ] All 3 IG permissions requested in single submission
- [ ] Submission notes mention "Instagram Login" / "OAuth" explicitly
- [ ] Screencast shows full OAuth flow (login → authorize → callback)
- [ ] Screencast shows Business Manager is SG CLOUD SpA (verified)
- [ ] Screencast shows end-to-end DM flow
- [ ] Screencast shows token refresh mechanism
- [ ] Test IG Professional account username provided in submission form
- [ ] Step-by-step test instructions provided
- [ ] All sensitive tokens/user IDs blurred
- [ ] Duration 5-15 minutes, English captions or narration

## Messenger App Review Addendum (if submitting in same review cycle)

For `pages_messaging` and `pages_manage_metadata` permissions.

Differences vs IG:
- Auth model: **Facebook Login** (not Instagram Login), but similar OAuth flow
- Test account: **FB Page** that the test user can message
- Token model: Page access token (long-lived, 60 days)

**Recommendation:** submit IG + Messenger in the same App Review submission — Meta allows multiple permission requests per submission. Saves a full review cycle.

Submission notes template is identical to IG section above, with these substitutions:
- Replace "Instagram Login" → "Facebook Login for Business"
- Replace `instagram_*` permissions → `pages_messaging`, `pages_manage_metadata`
- Replace IG Professional account → FB Page
- Replace `/{ig-user-id}/messages` → `/{page-id}/messages` via Send API

## Reference Links

- Instagram Messaging API: https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api
- Instagram API (Get Started): https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login
- Messenger Platform Overview: https://developers.facebook.com/documentation/business-messaging/messenger-platform/overview
- Messenger Platform Get Started: https://developers.facebook.com/documentation/business-messaging/messenger-platform/get-started
- Messenger Conversations API: https://developers.facebook.com/documentation/business-messaging/messenger-platform/conversations
- Permissions Reference: https://developers.facebook.com/docs/permissions/
- App Review: https://developers.facebook.com/docs/app-review

