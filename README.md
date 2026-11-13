# Sentinel Backend API

Unified Python backend for **Sentinel** — a mobile-first **AI Business Operations Platform** starting with Content Operations, Email + OTP Authentication, Social OAuth Login & Auto-Connect, and 100% server-side social publishing (**LinkedIn**, **X**, and **Instagram**).

---

## Architecture & Tech Stack

- **Framework:** FastAPI + Uvicorn (async)
- **Database:** PostgreSQL + Async SQLAlchemy 2.0 (`asyncpg`)
- **AI / LLM:** Google Gemini 2.5 Flash (`google-genai`) with structured Pydantic v2 outputs
- **Security:** `bcrypt` password hashing, PyJWT bearer tokens, HMAC-SHA256 Email OTPs, Fernet (`cryptography`) encryption for stored social OAuth tokens
- **Media:** Signed direct upload support for Cloudinary (images) and MUX (videos)
- **Package Management:** `uv` (`pyproject.toml` + `uv.lock`)

### OOP Design Patterns
- **Repository & Unit of Work:** `IUnitOfWork` / `SqlAlchemyUnitOfWork` wrapping `UserRepository`, `PostRepository`, `SocialAccountRepository`, `EmailOtpRepository`, and `OAuthIdentityRepository`.
- **Strategy + Factory:** `ISocialPublisher` (`LinkedInPublisher`, `XPublisher`, `InstagramPublisher`) resolved via `PublisherFactory` and orchestrated by `SocialPublishingService`.
- **Email Strategy:** `IEmailService` switching automatically between `ConsoleEmailService` (dev terminal output) and `ResendEmailService` (production).

---

## Project Structure

```text
backend/
├── .env.example
├── .gitignore
├── pyproject.toml
├── uv.lock
└── src/backend/
    ├── agents/            # ContentOperatorAgent (Gemini 2.5 Flash + fallback)
    ├── api/               # FastAPI routers (auth, posts, media, social)
    ├── core/              # Settings, async database manager, security & TokenCipher
    ├── models/            # SQLAlchemy 2.0 ORM models (users, posts, social_accounts, email_otps, oauth_identities)
    ├── repositories/      # Abstract & SQLAlchemy async repositories
    ├── schemas/           # Pydantic v2 request/response contracts
    ├── services/          # Email OTP delivery & OAuth login/auto-connect services
    ├── tools/
    │   └── publishers/    # Strategy-pattern social publishers (LinkedIn, X, Instagram)
    ├── unit_of_work/      # Atomic transaction boundary management
    ├── workers/           # ARQ background task definitions
    └── main.py            # FastAPI app entry point
```

---

## Local Setup

### 1. Install Dependencies
```powershell
uv sync
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and set your PostgreSQL credentials and API keys:
```powershell
Copy-Item .env.example .env
```
Make sure `sentinel_db` exists in PostgreSQL and `DATABASE_URL` in `.env` points to it *(note: URL-encode special characters in your password, such as `@` as `%40`)*.

### 3. Run the Development Server
```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

- **Health Check:** `http://localhost:8000/health`
- **Interactive Swagger Docs:** `http://localhost:8000/docs`

---

## Key API Routes (`/api/v1`)

| Group | Endpoints | Purpose |
| :--- | :--- | :--- |
| **Auth & OTP** | `POST /auth/register`, `POST /auth/verify-otp`, `POST /auth/resend-otp`, `POST /auth/login`, `GET /auth/me` | Signup with 6-digit email OTP verification before JWT issuance |
| **Social Login** | `GET /auth/oauth/{provider}`, `POST /auth/oauth/{provider}/callback`, `POST /auth/oauth/{provider}/sandbox` | Continue with Google / LinkedIn / X (auto-connects LinkedIn & X publishing) |
| **Social Connections** | `GET /social/accounts`, `GET /social/connect/{platform}`, `GET/POST /social/callback/{platform}`, `POST /social/connect/{platform}/sandbox`, `DELETE /social/accounts/{platform}` | Connect & manage in-app publishing accounts |
| **Posts & AI** | `POST /posts/generate`, `POST /posts/voice-draft`, `GET /posts`, `GET /posts/{post_id}`, `PUT /posts/{post_id}`, `POST /posts/{post_id}/schedule` | Text & Voice-to-Post generation for LinkedIn, X, and Instagram + server-side publishing |
| **Media** | `POST /media/upload-signature` | Generate direct upload signatures for Cloudinary / MUX |
