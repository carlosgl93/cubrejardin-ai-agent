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

