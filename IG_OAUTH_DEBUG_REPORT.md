# Instagram OAuth Connect — Debug Report

Channel: Instagram DM (IG Professional + FB Page)
Apps/IDs: see "Inventory" below
Repos: `cubrejardin-ai-agent` (backend), `astro-sg-cloud` (frontend)
Hosting: Cloud Run `whatsapp-api-250058155586.us-central1.run.app` + Firebase Hosting `sg-cloud-cefee.web.app`

## TL;DR

`/api/instagram/exchange` is end-to-end working **only when** the FBL v4 Embedded Signup popup completes and the frontend forwards the `sessionInfoListener` values (`page_id`, `ig_user_id`) to the backend. The backend writes them straight to Supabase and uses `FACEBOOK_PAGE_ACCESS_TOKEN` (sgcloudadmin system user, already owns Page 1028203907040559) as the page access token. **The Meta `oauth/access_token` exchange still happens** (and returns a system-user token for `Agents-Whtsapp System User`, FB-scoped `122098503459465178`), but the result is logged and **discarded** for the connection itself.

## Inventory

| Asset | ID |
| --- | --- |
| App (Agents-Whtsapp) | `1082408593965616` |
| IG business @sg_cloud_cl | `17841437785356540` |
| FB Page (SG Cloud) | `1028203907040559` |
| FBL v4 config (WA + IG features) | `1619575923013415` |
| WA FBL config (legacy) | `874698424915335` |
| sgcloudadmin system user (assigned page + IG) | `61587021125360` |
| sg_cloud_sysuser | `61573414405492` |
| Auto-created system user **that FBL binds codes to** | FB-scoped `122098503459465178` (display ID differs in Business Manager UI) |
| Business | `1146170093604782` (SG CLOUD SpA) |

Cloud Run env vars include `INSTAGRAM_IG_USER_ID=17841437785356540` and `INSTAGRAM_PAGE_ID=1028203907040559` (the latter is unused by code; kept for posterity).

## What was tested (chronological)

1. **Initial FBL popup with full WA flow** — config `1619575923013415` triggered the WA popup even with IG scopes. Rejected.
2. **`extras.feature: 'whatsapp_embedded_signup'`** — still showed WA. Switched to no-extras.
3. **`extras.feature: 'instagram_embedded_signup'` + config_id** — popup DID ask for IG account selection. ✓ Backend then 400'd with `"redirect_uri is identical"`.
4. **Removed `redirect_uri` from `/oauth/access_token`** — code→token exchange succeeded, but the long-lived token was `type: SYSTEM_USER` (`122098503459465178`) bound to "Agents-Whtsapp System User", not the consenting personal account.
5. **Tried adding @sg_cloud_cl as an asset on `sg_cloud_sysuser` (61573414405492)** — different system user than the token's; `/17841437785356540` still 400'd (code 100, subcode 33: "does not exist or missing permissions").
6. **`/me/accounts` with the long token returned `[]`** — system user has no pages provisioned even though we provisioned assets elsewhere.
7. **Dropped `config_id` to use standard OAuth (`response_type: 'code'`, `override_default_response_type: true`)** — popup then asked "which Pages to use" instead of "which Instagram account". Lost IG business linkage.
8. **Sent `redirect_uri` forward** — got "redirect_uri is identical" again (FB.login captured a different one during the popup).
9. **Tried `redirect_uri=https://www.facebook.com/connect/login_success.html`** — error 191 "The domain of this URL isn't included in the app's domains" (despite the URL being the SDK's well-known static target).
10. **Set `redirect_uri` explicitly to `https://localhost:4321/onboarding/`** — still 100/36008 "redirect_uri is identical".

## Current architecture (working end-to-end)

### Frontend (`astro-sg-cloud`)

`src/components/widgets/InstagramSignupButton.tsx`:
- Calls `FB.login` with FBL v4 Embedded Signup:
  ```ts
  FB.login(
    callback,
    {
      config_id: configId,            // 1619575923013415
      response_type: 'code',
      override_default_response_type: true,
      scope: 'instagram_manage_engagement,pages_messaging',
      extras: {
        feature: 'instagram_embedded_signup',
        sessionInfoListener: (info) => {
          pageId   = info.page_id   || '';
          igUserId = info.ig_user_id || '';
        },
      },
    },
  );
  ```
- Posts the resulting auth code + those two values to `/api/instagram/exchange`:
  ```ts
  body: JSON.stringify({
    auth_code,
    redirect_uri,
    config_id,
    page_id,
    ig_user_id,
  });
  ```

### Backend (`cubrejardin-ai-agent`)

`api/instagram.py` (`POST /api/instagram/exchange`):

1. Validate `auth_code`.
2. Exchange `code → short-lived token` via `/oauth/access_token`.
   - When `config_id` present → also send `config_id`; **omit `redirect_uri`** (FBL infers it, rejects if present).
   - When no `config_id` → standard OAuth, send `redirect_uri=https://www.facebook.com/connect/login_success.html`.
3. Exchange short → long-lived via `grant_type=fb_exchange_token`.
4. **Fast path (FBL):** if request has `page_id` + `ig_user_id` from `sessionInfoListener`, skip discovery:
   - `page_access_token = settings.facebook_page_access_token` (sgcloudadmin system user, already owns Page 1028203907040559 in this tenant's model).
   - Upsert `tenant_instagram_credentials` with `status='active'`, `page_id`, `ig_user_id`, expires-at, scrubbed token raw response, marker `"fbl_popup": true`.
   - **Return 200** with `{ig_user_id, page_id, status, token_expires_at}`.
5. **Slow path (fallback):** originally used when not coming from FBL popup. Walks `/me/accounts`, queries `instagram_business_account` per page, picks the first match. Long-token based. Still in code for future-proofing.

### Why the FBL long-lived token is discarded

`fb_exchange_token` against a code from FBL with `extras.feature=instagram_embedded_signup` returns a `type: SYSTEM_USER` token issued to the app's auto-created system user (FB-scoped `122098503459465178`). Even after assigning @sg_cloud_cl to `sg_cloud_sysuser (61573414405492)` via Business Manager, `/17841437785356540?fields=...` and `/me/accounts` both fail because **that specific system user is not the one we provisioned**. Trying to swap which system user gets the asset is a moving target because FBL re-binds to the auto-created one on each consent.

The pragmatic fix is to treat the popup sessionInfo as the source of truth for `page_id` + `ig_user_id`, and use the existing `FACEBOOK_PAGE_ACCESS_TOKEN` (sgcloudadmin) for actually talking to Meta on behalf of the page.

## How to test

### Pre-flight (verify)

1. App `1082408593965616` is live, not in dev mode lockout for your account.
2. `PUBLIC_INSTAGRAM_CONFIG_ID=1619575923013415` set in `.env` / GitHub secrets.
3. Valid OAuth Redirect URIs include the deployed domain (e.g., `https://sg-cloud-cefee.web.app/onboarding`).
4. `tenant_instagram_credentials` table allows the connection shape.

### End-to-end test on `sg-cloud-cefee.web.app`

1. Sign in, navigate to `/onboarding`.
2. Click **Connect Instagram**.
3. Popup should ask: "Which Instagram Professional account do you want to connect?" (not "which Pages").
4. Select `@sg_cloud_cl`. Finish.
5. Backend logs (`gcloud --project=sg-cloud-cefee logging read ... | grep ig.exchange`) should print:
   - `start tenant=... has_code=True config_id='1619575923013415' redirect_uri=... page_id='1028203907040559' ig_user_id='17841437785356540' ...`
   - `fbl_fast_path tenant=... page_id='1028203907040559' ig_user_id='17841437785356540'`
   - 200 response.
6. `GET /api/instagram/status` returns `instagram_connected: true`, the same ids, an expiry ~60 days out.

### If the popup reverts to "which Pages"

`config_id` was dropped from `FB.login` again, or the `sessionInfoListener` for `instagram_embedded_signup` is being shadowed. Pull latest `cubrejardin/ai-agent` `main` + `carlosgl93/astro-sg-cloud` `main`, redeploy both.

### If backend returns 502 with "Meta token exchange failed"

Re-check Cloud Run env: `FACEBOOK_TARGET_APP_ID`, `FACEBOOK_APP_SECRET`, `PUBLIC_INSTAGRAM_CONFIG_ID`. The current code path logs the Meta error body (first 1000 chars) before raising.

### If `/api/instagram/status` returns `instagram_connected: false` after a success

Look in Supabase `tenant_instagram_credentials` for a row with `status != 'active'`. The endpoint returns `instagram_connected: row.get('status') == 'active'`.

## Files touched (this work)

### Backend (`cubrejardin-ai-agent`)
- `api/instagram.py` — exchange endpoint (FBL fast path, fallback to token-based discovery).

### Frontend (`astro-sg-cloud`)
- `src/components/widgets/InstagramSignupButton.tsx` — FBL Embedded Signup with `extras.feature: 'instagram_embedded_signup'`, captures `page_id` + `ig_user_id` from `sessionInfoListener`, sends them in POST body.
- `src/components/widgets/OnboardingWizard.tsx` — `rawIgConfigId` env fallback + console warning if `PUBLIC_INSTAGRAM_CONFIG_ID` unset.
- `astro-sg-cloud/.env` — has `PUBLIC_FACEBOOK_CONFIG_ID`, `PUBLIC_INSTAGRAM_CONFIG_ID=1619575923013415`.

### Env / config (Cloud Run)
- `INSTAGRAM_IG_USER_ID=17841437785356540`
- `INSTAGRAM_PAGE_ID=1028203907040559`
- `FACEBOOK_PAGE_ACCESS_TOKEN=...`  (sgcloudadmin system user)

## Known gaps / next steps

1. **App Review**: scopes `instagram_manage_engagement`, `pages_messaging`, `read_page_mailboxes` will need App Review for non-admin users. Currently the admin (you) can consent without review.
2. **Page token rotation**: `page_access_token` is held on `tenant_instagram_credentials.page_access_token`. No auto-refresh yet. Long-lived user tokens on the page-side expire after ~60d. Long-lived page access tokens are eternal if generated as a page token from a long-lived user token, but our `FACEBOOK_PAGE_ACCESS_TOKEN` is a system-user token whose lifecycle TBD.
3. **Multi-tenant page ownership**: this build hardcodes a single tenant's page (`1028203907040559`) via `FACEBOOK_PAGE_ACCESS_TOKEN`. Multi-tenant will require per-tenant page token storage and rotation.
4. **WA IG hybrid config**: `1619575923013415` advertises both WA + IG. If you want a pure-IG config, create a new FBL v4 config with only `instagram_embedded_signup` selected. Cleaner separation, less confusion.

## Glossary / IDs cheat sheet

- `1082408593965616` — App.
- `1619575923013415` — FBL config id (WA + IG features).
- `874698424915335` — legacy WA config.
- `17841437785356540` — IG business account `@sg_cloud_cl`.
- `1028203907040559` — SG Cloud FB Page.
- `61587021125360` — sgcloudadmin system user (owns the page; used as `page_access_token`).
- `61573414405492` — sg_cloud_sysuser (Business Manager display id).
- `122098503459465178` — FB-scoped system user id **that FBL actually binds codes to** (different display id; not the one we provision in BM UI directly).
