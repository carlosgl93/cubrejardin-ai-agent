# Screencast Recording Script - Step by Step

## 🎥 Recording Checklist

- [ ] Set Meta Business Manager language to English
- [ ] Prepare demo WhatsApp number for testing
- [ ] Have test customer phone ready to send messages
- [ ] Clear browser cache/cookies for clean recording
- [ ] Close unnecessary tabs/applications
- [ ] Disable notifications during recording
- [ ] Test audio/microphone levels
- [ ] Use 1920x1080 resolution

---

## 🎬 Scene-by-Scene Script (Server-to-Server Version)

### **INTRO SCREEN** (10 seconds)
**Visual**: Title card or your app dashboard  
**Narration**: "This screencast demonstrates the server-to-server WhatsApp Business Management permission flow for CubreJardin AI Agent."

---

### **SCENE 1: Meta Business Manager Access** (2 minutes)

#### Step 1.1 - Login
**Visual**: Navigate to https://business.facebook.com  
**Action**: Log in with business account credentials
**Caption**: "Business owner logs into Meta Business Manager"  
**Narration**: "I'm logging into Meta Business Manager as the authorized business owner for CubreJardin."

#### Step 1.2 - Navigate to Settings
**Visual**: Click hamburger menu → Business Settings  
**Caption**: "Navigate to Business Settings"  
**Narration**: "From the Business Manager, I'll navigate to Business Settings."

#### Step 1.3 - Access System Users
**Visual**: Left sidebar → Users → System Users  
**Caption**: "System Users manage API access"  
**Narration**: "Under Users, we select System Users. This is where we manage programmatic API access for our application."

---

### **SCENE 2: System User & Permissions** (3 minutes)

#### Step 2.1 - Show Existing System User OR Create New
**Visual**: List of system users OR "Add" button  

**Action**: Click on existing system user  
**Caption**: "This system user has API access for our WhatsApp bot"  
**Narration**: "Here's the system user we've configured for our WhatsApp bot application. Let me show you its permissions."

#### Step 2.3 - View Permissions
**Visual**: Show assigned WhatsApp account with "Full control" badge  
**Caption**: "Full control includes whatsapp_business_management permission"  
**Narration**: "Full control grants the whatsapp_business_management permission, allowing our server to send and receive messages, manage phone numbers, and access business settings."

---

### **SCENE 3: Generate Access Token** (2 minutes)

#### Step 3.1 - Generate Token
**Visual**: Click "Generate New Token" button  
**Action**: Modal appears  
**Caption**: "Generating permanent access token"  
**Narration**: "Now I'll generate a permanent access token that our server will use to authenticate with WhatsApp Cloud API."

#### Step 3.2 - Select App & Permissions
**Visual**: Token generation modal  
**Action**:  
1. Select your app from dropdown
2. Check "whatsapp_business_management" permission
3. Set expiration (select "Never" for permanent)

**Caption**: "Selecting whatsapp_business_management permission"  
**Narration**: "I select our registered app and explicitly grant the whatsapp_business_management permission. This permission is critical for our bot to function."

#### Step 3.3 - Copy Token (blur it!)
**Visual**: Token appears, copy to clipboard  
**Action**: Click "Copy" → Token copied  
**Caption**: "Token generated (redacted for security)"  
**Narration**: "The token is generated. In production, this token is securely stored and never exposed to end users. I'm blurring it here for security."

---

### **SCENE 4: Server Configuration** (1 minute)

#### Step 4.1 - Show Environment Config
**Visual**: Open `.env.example` in code editor  
**Caption**: "Server-side token configuration"  
**Narration**: "The generated token is configured in our server's environment variables, specifically in the FACEBOOK_PAGE_ACCESS_TOKEN variable."

```bash
# Show this excerpt (with comments):
FACEBOOK_PAGE_ACCESS_TOKEN=EAAGxxxxxxxx  # ← Token goes here (server-side only)
WHATSAPP_PHONE_NUMBER_ID=123456789012345
```

**Narration (cont.)**: "Notice this is server-side configuration. There's no client-side login or browser-based authentication needed."

---

### **SCENE 5: Webhook Configuration** (2 minutes)

#### Step 5.1 - Navigate to WhatsApp Settings
**Visual**: Go back to Business Manager → WhatsApp Accounts → Configuration  
**Caption**: "Configuring webhook for message delivery"  
**Narration**: "Next, I'll configure the webhook so WhatsApp can notify our server when messages arrive."

#### Step 5.2 - Show Webhook Setup
**Visual**: Webhook configuration section  
**Action**: Show (don't edit if already configured):
- Callback URL: `https://your-domain.com/webhook/whatsapp`
- Verify Token: (matched with server config)
- Subscribed fields: messages, message_status

**Caption**: "Webhook receives incoming messages"  
**Narration**: "Our webhook endpoint receives incoming messages. The verify token ensures only Meta can send webhooks to our server."

#### Step 5.3 - Show Subscription Status
**Visual**: Green checkmark next to "messages" subscription  
**Caption**: "Webhook successfully verified and subscribed"  
**Narration**: "The green checkmark confirms our webhook is active and receiving message events."

---

### **SCENE 6: End-to-End Demo** (4 minutes)

#### Step 6.1 - Prepare Test
**Visual**: Split screen or picture-in-picture:
- Left: Phone with WhatsApp open
- Right: Server logs in terminal

**Caption**: "Demonstrating complete message flow"  
**Narration**: "Now let's see the end-to-end experience. I'll send a test message from a customer's phone and show how the bot processes and responds."

#### Step 6.2 - Send Customer Message
**Visual**: On phone, open WhatsApp chat with your business number  
**Action**: Type "¿Qué precio tiene el tiqui tiqui?" → Send  
**Caption**: "Customer asks: What's the price of tiqui tiqui?"  
**Narration**: "A customer sends a question about product pricing to our WhatsApp Business number."

#### Step 6.3 - Show Webhook Received
**Visual**: Switch to server terminal  
**Action**: Logs show incoming webhook  
```json
{
  "event": "whatsapp_message_received",
  "from": "+1234567890",
  "message": "¿Qué precio tiene el tiqui tiqui?",
  "message_id": "wamid.ABC123..."
}
```
**Caption**: "Server receives webhook from WhatsApp Cloud API"  
**Narration**: "Our server immediately receives the webhook event with the customer's message."

#### Step 6.4 - Show Processing
**Visual**: Continue showing logs  
**Action**: Logs show Guardian classification and RAG processing  
```json
{
  "event": "guardian_classification",
  "category": "VALID_QUERY"
}
{
  "event": "rag_answer",
  "confidence": 0.89,
  "sources": ["faqs.md"]
}
```
**Caption**: "Bot processes message using RAG"  
**Narration**: "The Guardian agent validates it's a legitimate question, then the RAG agent searches our knowledge base and generates a response with high confidence."

#### Step 6.5 - Show API Call to Send Response
**Visual**: Logs showing outgoing API call  
```json
{
  "event": "sending_message",
  "to": "+1234567890",
  "using_token": "FACEBOOK_PAGE_ACCESS_TOKEN",
  "permission": "whatsapp_business_management"
}
```
**Caption**: "Using whatsapp_business_management to send response"  
**Narration**: "The bot uses the whatsapp_business_management permission with our access token to send the response through WhatsApp Cloud API."

#### Step 6.6 - Show Customer Receives Response
**Visual**: Return to phone screen  
**Action**: Bot message appears in chat  
**Message**: "El Tiqui Tiqui tiene un precio de $690 por planta. Se necesitan 10 plantas por metro cuadrado, por lo que el costo por m² es de $6,900. ¿Te gustaría saber cuántas plantas necesitas para tu proyecto?"

**Caption**: "Customer receives automated response"  
**Narration**: "Within seconds, the customer receives an accurate, helpful response from our AI agent."

---

### **SCENE 7: Additional Permission Uses** (2 minutes)

#### Step 7.1 - Show Message Marking
**Visual**: Server logs  
```json
{
  "event": "mark_message_read",
  "message_id": "wamid.ABC123..."
}
```
**Caption**: "Marking message as read"  
**Narration**: "The bot also uses the permission to mark messages as read, providing a better user experience."

#### Step 7.2 - Template Message (Optional)
**Visual**: Send another message from phone after 24+ hours OR show code  
**Caption**: "Using approved templates outside 24-hour window"  
**Narration**: "Outside the 24-hour messaging window, the permission allows us to send pre-approved message templates."

#### Step 7.3 - Handoff to Human Agent (Optional)
**Visual**: Type "necesito hablar con un humano" on phone  
**Action**: Show handoff_notification template sent + pass_thread_control log  
**Caption**: "Transferring complex queries to human agents"  
**Narration**: "When customers request human support, the permission enables transferring the conversation to Page Inbox for our team to handle."

---

### **CONCLUSION** (30 seconds)
**Visual**: Summary slide or dashboard  
**Caption**: "End-to-end WhatsApp Business Management demonstrated"  
**Narration**: "This demonstrates the complete use of the whatsapp_business_management permission in our server-to-server application: token generation, webhook configuration, automated responses, and conversation management. Thank you."

---

## 📝 Submission Notes to Include

Copy this into your Facebook App Review submission:

```
APPLICATION TYPE: Server-to-Server (No frontend Meta login)

AUTHENTICATION:
This application uses a permanent Page Access Token generated by the business owner via Meta Business Manager. There is no end-user facing login flow.

TOKEN GENERATION PROCESS (shown in screencast):
1. Business owner logs into Meta Business Manager
2. Creates/accesses System User with admin privileges
3. Assigns WhatsApp Business Account to System User
4. Generates permanent token with whatsapp_business_management permission
5. Token configured server-side in environment variables

USE CASE:
WhatsApp AI Agent for CubreJardin customer support. Automatically responds to customer inquiries about products, pricing, and services via WhatsApp Cloud API.

PERMISSION USAGE DEMONSTRATED:
✓ Receiving messages via webhook (whatsapp_business_management)
✓ Sending text responses (whatsapp_business_management)
✓ Marking messages as read (whatsapp_business_management)
✓ Sending approved templates outside 24h window (whatsapp_business_management)
✓ Transferring conversations to human agents (whatsapp_business_management)

SCREENCAST CONTENTS:
- Meta Business Manager login and navigation
- System User creation/configuration
- whatsapp_business_management permission grant
- Token generation process
- Server-side configuration
- Complete message flow: receive → process → respond
- Webhook configuration and verification
- Live demonstration with real WhatsApp messages

All sensitive credentials are redacted in the screencast for security.
```

---

## 🎤 Recording Tips

### Audio Quality
- Use external microphone if possible
- Record in quiet room
- Speak clearly and at moderate pace
- Leave 1-2 second pauses between sections (easier to edit)

### Video Quality
- Use at least 1080p resolution
- 30fps minimum
- Don't move mouse too quickly
- Let important screens stay visible for 3-5 seconds
- Use zoom/highlight for small text

### Screen Recording Tools

**macOS:**
```bash
# QuickTime (built-in)
# File → New Screen Recording

# OBS Studio (free, powerful)
brew install --cask obs

# ScreenFlow (paid, professional)
# Available on Mac App Store
```

**Adding Captions:**
```bash
# iMovie (free on Mac)
# 1. Import video
# 2. Select clip → Titles → Lower Third
# 3. Customize text for each scene

# Final Cut Pro (paid)
# 1. Import → Add titles
# 2. Generator → Text → Custom
```

---

## ✅ Pre-Recording Checklist

1. **Environment Setup**
   - [ ] Meta Business Manager language set to English
   - [ ] All tabs closed except necessary ones
   - [ ] Notifications disabled (Do Not Disturb mode)
   - [ ] Desktop clean (no confidential items visible)
   - [ ] Terminal ready with server running
   - [ ] Test phone has WhatsApp open

2. **Test Run**
   - [ ] Do a practice run (don't record yet)
   - [ ] Ensure all steps work smoothly
   - [ ] Check token generation works
   - [ ] Verify webhook receives messages
   - [ ] Confirm bot responds correctly

3. **Recording Setup**
   - [ ] Recording software configured (1920x1080, 30fps)
   - [ ] Microphone tested
   - [ ] Script printed or on second monitor
   - [ ] Timer ready (aim for 8-12 minutes total)

4. **Security**
   - [ ] Real tokens will be blurred in post-production OR
   - [ ] Use test app with temporary tokens
   - [ ] No passwords visible on screen
   - [ ] .env file shows .env.example only

---

## 🛠️ Post-Production Checklist

1. **Editing**
   - [ ] Trim dead air/mistakes
   - [ ] Add text captions for each major step
   - [ ] Blur/redact all sensitive tokens
   - [ ] Add zoom/highlight to important areas
   - [ ] Ensure total length is 8-15 minutes

2. **Review**
   - [ ] Watch entire video
   - [ ] Verify audio levels consistent
   - [ ] Check all captions are readable
   - [ ] Confirm credentials are hidden
   - [ ] Validate flow is clear and logical

3. **Export**
   - [ ] Format: MP4 (H.264)
   - [ ] Resolution: 1920x1080
   - [ ] Bitrate: 5-10 Mbps
   - [ ] File size: Under 1GB if possible

---

## 📤 Submission Process

1. **Upload Video**: Use WeTransfer, Google Drive, or Facebook's uploader
2. **Paste Submission Notes**: Use the template above
3. **Additional Details**: Mention no frontend login in every text field
4. **Submit**: Click submit and wait for review (typically 3-7 days)

---

## ❓ Troubleshooting

**Q: Video is too long (>15 min)?**  
A: Speed up sections where you're waiting (2x speed in editing)

**Q: Forgot to blur a token?**  
A: Use blur effect in iMovie/DaVinci Resolve or re-record that section

**Q: No WhatsApp messages received in demo?**  
A: Check webhook logs first, verify subscription, test with curl before recording

**Q: Facebook rejects again?**  
A: Read feedback carefully, focus on what's missing, consider implementing OAuth if they insist on login flow

---

## 📞 Need Help?

Review these resources:
- [Meta App Review Docs](https://developers.facebook.com/docs/app-review)
- [WhatsApp Cloud API Permissions](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started#permissions)
- [Screen Recording Guide](https://developers.facebook.com/docs/app-review/screencast)

Good luck with your app review! 🚀
