# FE Handoff: Authentication

> Branch: `dev`
> Date: 2026-06-05

## 1) Endpoint map

- `POST /auth/register` — Register with email (async verification email sent)
- `POST /auth/register-username` — Register with username only, get token immediately
- `POST /auth/login` — Login with email + password
- `POST /auth/login-username` — Login with username + password
- `GET /auth/verify` — Verify email via token from verification link
- `POST /auth/resend-verification` — Resend verification email (no email enumeration)
- `GET /auth/google` — Get Google OAuth authorization URL
- `GET /auth/google/callback` — Google OAuth callback (redirects to frontend with token)

## 2) Contracts

### Email Registration

`POST /auth/register`

**Auth:** None (public endpoint)

**Body:**
```json
{
  "email": "user@example.com",
  "password": "securepass123"
}
```

Validation rules:
- `email` — must be valid email format
- `password` — minimum 8 characters

**Response `data` (201 Created):**
```json
{
  "id": 1,
  "email": "user@example.com",
  "username": null,
  "is_active": true,
  "is_verified": false,
  "goals": [],
  "display_name": null,
  "avatar_url": null,
  "timezone": null
}
```

**FE notes:**
- Email verification link is sent asynchronously after response
- Show message: "Check your email to verify your account"
- User cannot login until `is_verified` is true

---

### Username Registration

`POST /auth/register-username`

**Auth:** None (public endpoint)

**Body:**
```json
{
  "username": "john_doe",
  "password": "securepass123"
}
```

Validation rules:
- `username` — 3–50 characters, alphanumeric + hyphens + underscores only
- `password` — minimum 8 characters

**Response (201 Created):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiI...",
  "token_type": "bearer"
}
```

**FE notes:**
- User is active immediately, no email verification required
- Store token in localStorage/secure cookie
- Include token in `Authorization: Bearer <token>` header for authenticated requests
- Consider prompting user to add email later for account recovery

---

### Email Login

`POST /auth/login`

**Auth:** None (public endpoint)

**Body:**
```json
{
  "email": "user@example.com",
  "password": "securepass123"
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiI...",
  "token_type": "bearer"
}
```

**FE notes:**
- Store token in localStorage/secure cookie
- Include token in `Authorization: Bearer <token>` header for authenticated requests

---

### Username Login

`POST /auth/login-username`

**Auth:** None (public endpoint)

**Body:**
```json
{
  "username": "john_doe",
  "password": "securepass123"
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiI...",
  "token_type": "bearer"
}
```

**FE notes:**
- Same as email login; token is used for all authenticated requests
- Store token securely

---

### Email Verification

`GET /auth/verify`

**Auth:** None (public endpoint, uses token query param)

**Query params:**
| Param | Type | Required | Note |
|-------|------|----------|------|
| `token` | string | yes | Verification token from email link |

**Response (200 OK):**
```json
{
  "message": "Email verified successfully. You can now log in."
}
```

**FE notes:**
- Link format: `{FRONTEND_URL}/auth/verify?token=<token_from_email>`
- After verification, show success message and redirect to login

---

### Resend Verification Email

`POST /auth/resend-verification`

**Auth:** None (public endpoint)

**Body:**
```json
{
  "email": "user@example.com"
}
```

**Response (200 OK):**
```json
{
  "message": "If that email is registered and unverified, a new link has been sent."
}
```

**FE notes:**
- **Always returns same success message** (email enumeration prevention)
- Email is only sent if account exists AND is unverified
- User should check email shortly

---

### Google OAuth — Get Authorization URL

`GET /auth/google`

**Auth:** None (public endpoint)

**Query params:** None

**Response (200 OK):**
```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=..."
}
```

**FE notes:**
- Redirect browser to `authorization_url`
- Google will ask user to sign in and grant permissions
- After user grants, Google redirects to `/auth/google/callback`

---

### Google OAuth — Callback Handler

`GET /auth/google/callback`

**Auth:** None (public endpoint, uses code query param)

**Query params:**
| Param | Type | Required | Note |
|-------|------|----------|------|
| `code` | string | yes | Authorization code from Google |

**Response (302 Redirect):**
- **On success:** Redirect to `{FRONTEND_URL}/auth/google/callback?token=<access_token>`
- **On error:** Redirect to `{FRONTEND_URL}/login?error=<error_message>`

**FE notes:**
- This is a server-side callback; FE only needs to handle the redirect
- Extract token from query param and store it (same as email/username login)
- If `error` param present, show error message to user
- Suggested flow: `GET /auth/google` → user signs in at Google → backend redirects with token

---

## 3) Error codes

| HTTP | Message | When |
|------|---------|------|
| 400 | Invalid verification link | Token not found or wrong format |
| 400 | Verification link has expired | Token expired (24 hour TTL) |
| 400 | Email is already verified | Resend called on already-verified account |
| 401 | Invalid credentials | Email/username or password incorrect |
| 403 | Please verify your email before logging in | Login attempted before email verification (email flow only) |
| 403 | Account is deactivated | Login attempted on deactivated account |
| 409 | Email already registered | Registration with email that exists |
| 409 | Username already taken | Registration with username that exists |
| 422 | Password must be at least 8 characters | Validation error |
| 422 | Username must be at least 3 characters | Validation error |
| 422 | Username may only contain letters, numbers, hyphens, and underscores | Validation error |

---

## 4) FE notes

### Flow recommendations

**Email + Password flow:**
1. User fills register form → `POST /auth/register`
2. Show "Check your email" message
3. User clicks email link → GET `/auth/verify?token=...`
4. Show "Verified! Go to login"
5. User logs in → `POST /auth/login`
6. Store token, redirect to app

**Username-only flow:**
1. User fills register form → `POST /auth/register-username`
2. Token returned immediately
3. Store token, redirect to app (no email step needed)
4. Optionally prompt to add email later for recovery

**Google OAuth flow:**
1. Show "Sign in with Google" button
2. Click → `GET /auth/google` to get authorization_url
3. Redirect browser to authorization_url
4. User completes sign-in at Google
5. Backend redirects to `{FRONTEND_URL}/auth/google/callback?token=...`
6. Extract token and store it

### Key behaviors

- **Token storage:** Store JWT in localStorage or secure httpOnly cookie. Use in `Authorization: Bearer <token>` header.
- **Email enumeration prevention:** Resend endpoint always returns success message even if email not found.
- **Credential validation:** Register/login return same "Invalid credentials" for both wrong email/username AND wrong password.
- **Token expiration:** Tokens are JWTs; check client-side expiry before using. If expired, show login prompt.
- **Google users cannot use email login:** If user registered via Google, email login will return 400 "This account uses Google login...".

### Common errors & handling

| Error | Show user | Next action |
|-------|-----------|-------------|
| 409 Email/Username taken | "This email/username is already taken" | Suggest login instead |
| 401 Invalid credentials | "Email/username or password incorrect" | Show form again |
| 403 Not verified | "Please verify your email first. [Resend link]" | Link to resend endpoint |
| 403 Account deactivated | "Your account has been deactivated" | Contact support |
