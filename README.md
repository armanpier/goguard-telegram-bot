# 🚀 GoGuard Telegram Bot (Mirzabot Workflow)

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Aiogram](https://img.shields.io/badge/aiogram-3.x-2C3E50.svg)](https://docs.aiogram.dev/)
[![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A complete, production-ready Telegram Bot written in Python for selling and managing VPN/Proxy subscriptions integrated directly with the **GoGuard Panel API 1.0** (inspired by the battle-tested workflow of **mirzabot**).

---

## 📑 Table of Contents
- [✨ Key Features](#-key-features)
- [🏗 Architecture & Workflow](#-architecture--workflow)
- [🔌 GoGuard Panel API 1.0 Integration](#-goguard-panel-api-10-integration)
- [📦 Project Structure](#-project-structure)
- [🚀 Quick Start Guide](#-quick-start-guide)
  - [Method 1: Docker Compose (Recommended)](#method-1-docker-compose-recommended)
  - [Method 2: Linux VPS / Local Python](#method-2-linux-vps--local-python)
- [⚙️ Configuration Reference (.env)](#️-configuration-reference-env)
- [🧪 Running Unit Tests](#-running-unit-tests)
- [📄 License](#-license)

---

## ✨ Key Features

### 👤 For Customers & Users
- 🛒 **Plan Catalog:** Interactive listing of available subscription plans with duration, traffic (GB), and pricing.
- 💳 **Multiple Payment Options:**
  - **کارت به کارت (Card-to-Card):** Displays admin bank card details (copyable monospace) and accepts photo receipts with instant admin review.
  - **کیف پول (Wallet Balance):** Instant 1-click subscription delivery from pre-funded wallet balance.
- ⚡️ **Instant Provisioning:** Immediate GoGuard API subscription provisioning upon payment approval.
- 📱 **QR Code Delivery:** In-memory QR code generation for direct scanning into mobile apps (V2RayNG, Streisand, FoXray, Shadowrocket, v2rayN).
- 📊 **Live Service Monitor (سرویس‌های من):** Real-time traffic query from GoGuard API with visual usage progress bar (`[██████░░░░] 60%`), remaining volume, and Jalali expiry dates.
- 🔄 **Subscription Renewal:** One-click renewal that extends existing GoGuard data limits and expiry timestamps.
- 🎁 **Free Trial (تست رایگان):** Automated 24-hour / 1GB trial account provisioning with anti-abuse (one trial per Telegram ID).
- 🤝 **Affiliate & Referral System:** Unique invite link (`/start ref_<user_id>`) with automated percentage commission credited to referrer wallet.
- 📚 **Setup Guides:** Step-by-step connection tutorials for Android, iOS, Windows, and macOS.
- 📢 **Force-Join Channel:** Optional mandatory Telegram channel subscription check before bot access.

### 🌐 Modern WebUI Admin Panel (FastAPI + Tailwind RTL)
- 📊 **Executive Dashboard:** Live KPIs (total users, active subs, total sales, pending receipts), GoGuard Panel API connectivity status widget.
- ⚙️ **Dynamic Settings Management:** Real-time modification of bank card details, GoGuard credentials, support ID, channel ID, free trial quotas, and referral percentages without bot restarts.
- 💳 **Receipt Moderation:** Filterable receipt feed (All / Pending / Approved / Rejected) with Telegram image preview and 1-click approve/reject actions.
- 📦 **Plan Catalog Management:** Create new plans, toggle active/inactive status, and delete plans.
- 👥 **User Management:** Instant user search (by Telegram ID or username), wallet balance credit/debit adjustment, and ban/unban toggles.
- 🔗 **Subscriptions Overview:** View all issued client accounts, real-time sync with GoGuard Panel, and deletion.

### 👑 For Administrators via Telegram (`/admin`)
- 📊 **Bot Analytics:** Real-time statistics on total registered users, active subscriptions, pending receipts, and total sales.
- 💳 **Receipt Moderation:** Immediate notification when a user submits a receipt photo with inline `[✅ تایید و فعال‌سازی]` and `[❌ رد پرداخت]` buttons.
- 📦 **Plan Management (CRUD):** Add, toggle active/inactive, or delete plans right from Telegram without restarting the bot.
- 📢 **Mass Broadcast:** Asynchronous rate-limited message broadcasting to all bot users with progress reporting.
- 🌐 **GoGuard Panel Diagnostics:** Live API health check and token authentication status test.
- 🔙 **Consistent Navigation:** Standardized **"بازگشت"** button across all conversational states.

---

## 🏗 Architecture & Workflow

```mermaid
flowchart TD
    User([Telegram User]) -->|Browse Plans & Buy| Bot[Telegram Bot Engine (aiogram 3.x)]
    Bot -->|Card-to-Card Receipt| Admin([Admin])
    Admin -->|Approve Receipt| Bot
    User -->|Pay with Wallet Balance| Bot
    Bot -->|Auth & Token Auto-Refresh| GGClient[GoGuardClient API 1.0]
    GGClient -->|POST /api/subscriptions| Panel[(GoGuard Panel API)]
    Panel -->|Subscription URL & Token| GGClient
    GGClient --> Bot
    Bot -->|Generate QR Code & Sub Link| User
    User -->|View Live Traffic| Bot
    Bot -->|GET /api/subscriptions/username| Panel
```

---

## 🔌 GoGuard Panel API 1.0 Integration

The application contains a robust, asynchronous client in [`app/services/goguard.py`](file:///c:/Users/Arman/Documents/antigravity/kind-pythagoras/app/services/goguard.py) adhering to the GoGuard API 1.0 specifications:

1. **Authentication Endpoint:**
   - `POST /api/admins/token`
   - Payload: `{"username": "...", "password": "..."}`
   - Response: `{"token": "...", "token_type": "Bearer", "expires_at": "..."}`
2. **Client Header:**
   - Every request passes `Authorization: Bearer <token>`.
3. **Resilient Token Management:**
   - Thread/async-safe authentication with `asyncio.Lock`.
   - Token freshness check with a 30-second buffer before requests.
   - **Automatic 401 Unauthorized Interceptor:** Automatically refreshes the bearer token and retries failed requests without interrupting the user.
4. **Subscription Provisioning:**
   - `POST /api/subscriptions`
   - Payload Schema:
     ```json
     {
       "username": "u123456_a9b8c7",
       "data_limit": 10737418240,
       "expire": 1775730000,
       "status": "active",
       "note": "Plan: 1 Month 30GB | TG: 123456"
     }
     ```
   - Traffic conversion: Gigabytes are converted to **Bytes** (`GB * 1024^3`).
   - Expiration conversion: Days are converted to **Epoch Unix Timestamp** in seconds.

---

## 📦 Project Structure

```
goguard-telegram-bot/
├── app/
│   ├── __init__.py
│   ├── main.py                  # Bot entry point, dispatcher & polling
│   ├── config.py                # Pydantic Settings (.env loader & validator)
│   ├── database/
│   │   ├── __init__.py
│   │   ├── session.py           # Async SQLAlchemy engine & session factory
│   │   └── models.py            # User, Plan, Subscription, PaymentReceipt, Setting
│   ├── services/
│   │   ├── __init__.py
│   │   ├── goguard.py           # GoGuard Panel API 1.0 async client
│   │   ├── subscription.py      # Provisioning & sync business logic
│   │   ├── payment.py           # Receipt moderation & referral commission
│   │   └── qr.py                # In-memory QR code generator
│   └── bot/
│       ├── __init__.py
│       ├── middlewares/         # Database, Auth & Throttling middlewares
│       ├── keyboards/           # Reply & Inline markup buttons
│       ├── states/              # FSM States (Receipts, Plans, Broadcast)
│       ├── handlers/            # Start, User, Payment, Admin, Error handlers
│       └── utils/               # Formatters (Bytes, Jalali, Progress Bar) & Texts
├── tests/
│   ├── test_goguard_api.py      # Unit tests for GoGuard Client & 401 refresh
│   └── test_formatters.py       # Unit tests for byte conversions & Jalali dates
├── systemd/
│   └── goguard-bot.service      # Systemd service unit for VPS deployment
├── .env.example                 # Configuration template
├── .gitignore                   # Git ignore file
├── Dockerfile                   # Multi-stage production container
├── docker-compose.yml           # Docker Compose orchestrator
├── requirements.txt             # Python dependencies
└── pyproject.toml               # Package specifications
```

---

## 🚀 Quick Start Guide

### ⚡ Method 1: Interactive Installation Wizard (Recommended)

Simply run the interactive installer which prompts for your **Telegram Bot Token**, **Admin Telegram IDs**, **GoGuard Panel URL & Credentials** (with real-time API connection validation), and writes your `.env` automatically:

#### On Linux VPS:
```bash
git clone https://github.com/armanpier/goguard-telegram-bot.git
cd goguard-telegram-bot
bash install.sh
```

#### On Windows / Any Platform:
```bash
git clone https://github.com/armanpier/goguard-telegram-bot.git
cd goguard-telegram-bot
python setup.py
```

The wizard will:
1. Validate your **Telegram Bot Token** in real-time against `api.telegram.org`.
2. Format and validate your **Admin Telegram IDs**.
3. Authenticate with your **GoGuard Panel API 1.0** live (`POST /api/admins/token`) to verify connection.
4. Prompt for bank card details, free trial options, and referral settings.
5. Generate your production `.env` and offer to launch via Docker Compose or Python!

---

### 🐳 Method 2: Manual Docker Compose

1. **Clone the repository:**
   ```bash
   git clone https://github.com/armanpier/goguard-telegram-bot.git
   cd goguard-telegram-bot
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   nano .env
   ```
   Fill in your `BOT_TOKEN`, `ADMIN_IDS`, `GOGUARD_BASE_URL`, `GOGUARD_USERNAME`, and `GOGUARD_PASSWORD`.

3. **Start the bot container:**

   ```bash
   docker compose up -d --build
   ```

4. **View logs:**
   ```bash
   docker compose logs -f
   ```

---

### Method 2: Linux VPS / Local Python

1. **Ensure Python 3.11+ is installed:**
   ```bash
   python3 --version
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Configure `.env` file:**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

5. **Run the bot:**
   ```bash
   python -m app.main
   ```

---

## ⚙️ Configuration Reference (`.env`)

| Variable | Type | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | String | *Required* | Telegram Bot token obtained from [@BotFather](https://t.me/BotFather) |
| `ADMIN_IDS` | CSV List | *Required* | Comma-separated Telegram User IDs with admin access |
| `GOGUARD_BASE_URL` | String | `https://core.erfjab.com` | Base URL of your GoGuard Panel |
| `GOGUARD_USERNAME` | String | *Required* | GoGuard Admin username |
| `GOGUARD_PASSWORD` | String | *Required* | GoGuard Admin password |
| `GOGUARD_SUB_URL_TEMPLATE` | String | `{base_url}/sub/{username}` | Fallback subscription URL template |
| `DATABASE_URL` | String | `sqlite+aiosqlite:////app/data/bot.db` | SQLAlchemy connection string |
| `WEB_ENABLE` | Boolean | `true` | Enable or disable the WebUI Admin Panel |
| `WEB_PORT` | Integer | `8080` | Port for the WebUI Admin Panel |
| `WEB_USERNAME` | String | `admin` | Admin username for WebUI login |
| `WEB_PASSWORD` | String | `admin123` | Admin password for WebUI login |
| `WEB_SECRET_KEY` | String | *Auto-generated* | Secret key for signing admin session cookies |
| `CARD_NUMBER` | String | `6037-9918-0000-0000` | Bank card number for manual transfers |
| `CARD_HOLDER` | String | `نام دارنده کارت` | Name of the bank card holder |
| `CURRENCY_TITLE` | String | `تومان` | Display currency name (e.g. تومان, IRT) |
| `REQUIRED_CHANNEL_ID` | String | `None` | Optional channel username for force-join (e.g. `@mychannel`) |
| `FREE_TRIAL_ENABLED` | Boolean | `true` | Enable or disable free trial account creation |
| `FREE_TRIAL_TRAFFIC_GB` | Float | `1.0` | Traffic quota allocated for trial accounts in GB |
| `FREE_TRIAL_DURATION_DAYS` | Integer | `1` | Validity period for trial accounts in days |
| `REFERRAL_ENABLED` | Boolean | `true` | Toggle user referral affiliate program |
| `REFERRAL_COMMISSION_PERCENT`| Integer | `10` | Referral commission percentage credited to wallet |

---

## 🧪 Running Unit Tests

Run the test suite using `pytest`:

```bash
pytest -v
```

All 18 unit tests will execute, validating:
- GoGuard admin token parsing and headers.
- GoGuard automatic token refresh on 401 Unauthorized responses.
- Accurate byte conversion (`GB -> Bytes`) and Unix epoch timestamps.
- Alphanumeric GoGuard username generation (`^[a-z0-9]+$`) and clean ASCII notes.
- WebUI HMAC session cookie authentication and route protection.
- Dynamic runtime settings database persistence and `.env` fallbacks.
- Jalali date conversions, progress bars, and currency formatting.

---

## 📄 License
This project is open-source and released under the [MIT License](LICENSE).
