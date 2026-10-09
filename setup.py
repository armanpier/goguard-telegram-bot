#!/usr/bin/env python3
"""
Interactive Installation & Configuration Wizard for GoGuard Telegram Bot.
Collects and validates Bot Token, Admin IDs, GoGuard Credentials, and settings,
generating the production .env file and optionally starting the service.
"""

import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


# ANSI Color Codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def print_banner():
    banner = f"""{CYAN}{BOLD}
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║     🚀 GoGuard Telegram Bot - Interactive Setup Wizard          ║
║     Integrated with GoGuard Panel API 1.0 (Mirzabot Workflow)   ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝{RESET}
"""
    print(banner)


def prompt_input(prompt: str, default: str = "", required: bool = True) -> str:
    default_hint = f" [{default}]" if default else ""
    while True:
        try:
            val = input(f"{BOLD}{prompt}{default_hint}: {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{YELLOW}Installation aborted by user.{RESET}")
            sys.exit(0)

        if not val and default:
            return default
        if not val and required:
            print(f"{RED}⚠️ This field is required. Please provide a value.{RESET}")
            continue
        return val


def prompt_password(prompt: str, default: str = "", required: bool = True) -> str:
    default_hint = " [Leave blank to keep existing]" if default else ""
    while True:
        try:
            val = getpass.getpass(f"{BOLD}{prompt}{default_hint}: {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{YELLOW}Installation aborted by user.{RESET}")
            sys.exit(0)

        if not val and default:
            return default
        if not val and required:
            print(f"{RED}⚠️ Password is required.{RESET}")
            continue
        return val


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            val = input(f"{BOLD}{prompt} {hint}: {RESET}").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{YELLOW}Installation aborted by user.{RESET}")
            sys.exit(0)

        if not val:
            return default
        if val in ("y", "yes", "true", "1"):
            return True
        if val in ("n", "no", "false", "0"):
            return False
        print(f"{YELLOW}Please enter 'y' or 'n'.{RESET}")


def validate_telegram_bot_token(token: str) -> tuple[bool, str]:
    """Test token against Telegram Bot API getMe."""
    print(f"⏳ Verifying Telegram Bot token...")
    url = f"https://api.telegram.org/bot{token}/getMe"
    req = urllib.request.Request(url, headers={"User-Agent": "GoGuard-Setup-Wizard/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data.get("ok"):
                bot_user = data["result"].get("username", "Unknown")
                bot_name = data["result"].get("first_name", "Bot")
                return True, f"@{bot_user} ({bot_name})"
            return False, data.get("description", "Unknown error")
    except urllib.error.HTTPError as e:
        try:
            err_data = json.loads(e.read().decode())
            return False, err_data.get("description", f"HTTP {e.code}")
        except Exception:
            return False, f"HTTP Error {e.code}"
    except Exception as e:
        return False, f"Connection error: {e}"


def validate_goguard_credentials(base_url: str, username: str, password: str) -> tuple[bool, str]:
    """Test GoGuard Panel credentials with POST /api/admins/token."""
    clean_url = base_url.rstrip("/")
    login_url = f"{clean_url}/api/admins/token"
    print(f"⏳ Verifying GoGuard API connection at {login_url}...")

    payload = json.dumps({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        login_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "GoGuard-Setup-Wizard/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
            if "token" in data or "access_token" in data:
                return True, "Successfully authenticated with GoGuard Panel API."
            return False, f"Unexpected response: {data}"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, "Invalid username or password (401 Unauthorized)."
        try:
            err_body = e.read().decode()
            return False, f"Panel returned HTTP {e.code}: {err_body}"
        except Exception:
            return False, f"Panel returned HTTP {e.code}"
    except Exception as e:
        return False, f"Could not reach panel: {e}"


def load_existing_env() -> dict[str, str]:
    """Load existing .env values if file exists."""
    existing = {}
    if os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        existing[k.strip()] = v.strip().strip('"').strip("'")
        except Exception:
            pass
    return existing


def main():
    clear_screen()
    print_banner()

    existing = load_existing_env()
    if existing:
        print(f"{YELLOW}ℹ️ Found existing .env file. Press Enter on any field to keep the current value.{RESET}\n")

    # =========================================================================
    # Step 1: Telegram Bot Configuration
    # =========================================================================
    print(f"\n{BOLD}{CYAN}=== Step 1: Telegram Bot Configuration ==={RESET}")
    print("Get your bot token from @BotFather on Telegram.")

    bot_token = ""
    while True:
        bot_token = prompt_input(
            "Enter Telegram BOT_TOKEN",
            default=existing.get("BOT_TOKEN", ""),
            required=True,
        )

        ok, info = validate_telegram_bot_token(bot_token)
        if ok:
            print(f"{GREEN}✓ Valid Bot Token! Connected as {info}{RESET}")
            break
        else:
            print(f"{RED}✗ Telegram API check failed: {info}{RESET}")
            if prompt_yes_no("Do you want to use this token anyway?", default=False):
                break

    # Admin IDs
    admin_ids_str = ""
    while True:
        admin_ids_str = prompt_input(
            "Enter ADMIN_IDS (comma-separated Telegram User IDs, e.g. 123456789,987654321)",
            default=existing.get("ADMIN_IDS", ""),
            required=True,
        )
        # Validate format
        parts = [p.strip() for p in admin_ids_str.split(",") if p.strip()]
        if not parts or not all(p.lstrip("-").isdigit() for p in parts):
            print(f"{RED}⚠️ Invalid format. Please enter numeric user IDs separated by commas.{RESET}")
            continue
        admin_ids_str = ",".join(parts)
        print(f"{GREEN}✓ Configured {len(parts)} admin ID(s): {admin_ids_str}{RESET}")
        break

    # Support Username
    support_username = prompt_input(
        "Enter Support Telegram Username",
        default=existing.get("SUPPORT_USERNAME", "@vpn_support"),
        required=False,
    )
    if not support_username.startswith("@") and support_username:
        support_username = f"@{support_username}"

    # Required Channel (Optional)
    required_channel = prompt_input(
        "Enter Required Channel ID/Username for mandatory membership (optional, leave blank to disable)",
        default=existing.get("REQUIRED_CHANNEL_ID", ""),
        required=False,
    )

    # =========================================================================
    # Step 2: GoGuard Panel API 1.0 Credentials
    # =========================================================================
    print(f"\n{BOLD}{CYAN}=== Step 2: GoGuard Panel API 1.0 Configuration ==={RESET}")
    print("Provide your GoGuard Panel address and admin credentials.")

    base_url = ""
    username = ""
    password = ""

    while True:
        base_url = prompt_input(
            "Enter GoGuard Base URL",
            default=existing.get("GOGUARD_BASE_URL", "https://core.erfjab.com"),
            required=True,
        ).rstrip("/")

        username = prompt_input(
            "Enter GoGuard Admin Username",
            default=existing.get("GOGUARD_USERNAME", "admin"),
            required=True,
        )

        password = prompt_password(
            "Enter GoGuard Admin Password",
            default=existing.get("GOGUARD_PASSWORD", ""),
            required=True,
        )

        ok, msg = validate_goguard_credentials(base_url, username, password)
        if ok:
            print(f"{GREEN}✓ {msg}{RESET}")
            break
        else:
            print(f"{RED}✗ GoGuard authentication check failed: {msg}{RESET}")
            if prompt_yes_no("Do you want to proceed with these credentials anyway?", default=False):
                break

    sub_template = prompt_input(
        "Enter Subscription URL Template",
        default=existing.get("GOGUARD_SUB_URL_TEMPLATE", "{base_url}/sub/{username}"),
        required=False,
    )

    # =========================================================================
    # Step 3: Payment & Bank Card Details
    # =========================================================================
    print(f"\n{BOLD}{CYAN}=== Step 3: Payment & Bank Card Settings ==={RESET}")
    card_number = prompt_input(
        "Enter Bank Card Number for Card-to-Card payments",
        default=existing.get("CARD_NUMBER", "6037-9918-0000-0000"),
        required=False,
    )

    card_holder = prompt_input(
        "Enter Cardholder Name",
        default=existing.get("CARD_HOLDER", "مدیریت"),
        required=False,
    )

    currency_title = prompt_input(
        "Enter Currency Title",
        default=existing.get("CURRENCY_TITLE", "تومان"),
        required=False,
    )

    # =========================================================================
    # Step 4: Free Trial & Referral Settings
    # =========================================================================
    print(f"\n{BOLD}{CYAN}=== Step 4: Trial & Affiliate Settings ==={RESET}")
    free_trial = prompt_yes_no(
        "Enable Free Trial (test accounts)?",
        default=existing.get("FREE_TRIAL_ENABLED", "true").lower() == "true",
    )

    trial_traffic = "1.0"
    trial_days = "1"
    if free_trial:
        trial_traffic = prompt_input(
            "Free Trial Traffic in GB",
            default=existing.get("FREE_TRIAL_TRAFFIC_GB", "1.0"),
            required=False,
        )
        trial_days = prompt_input(
            "Free Trial Duration in Days",
            default=existing.get("FREE_TRIAL_DURATION_DAYS", "1"),
            required=False,
        )

    referral_enabled = prompt_yes_no(
        "Enable Referral / Affiliate Program?",
        default=existing.get("REFERRAL_ENABLED", "true").lower() == "true",
    )

    ref_percent = "10"
    if referral_enabled:
        ref_percent = prompt_input(
            "Referral Commission Percentage",
            default=existing.get("REFERRAL_COMMISSION_PERCENT", "10"),
            required=False,
        )

    # Database
    db_url = prompt_input(
        "Database URL",
        default=existing.get("DATABASE_URL", "sqlite+aiosqlite:///bot.db"),
        required=False,
    )

    # =========================================================================
    # Save .env File
    # =========================================================================
    print(f"\n{BOLD}{CYAN}=== Saving Configuration ==={RESET}")

    env_content = f"""# ==========================================
# Telegram Bot Configuration
# ==========================================
BOT_TOKEN={bot_token}
ADMIN_IDS={admin_ids_str}
SUPPORT_USERNAME={support_username}
REQUIRED_CHANNEL_ID={required_channel}

# ==========================================
# GoGuard Panel API 1.0 Configuration
# ==========================================
GOGUARD_BASE_URL={base_url}
GOGUARD_USERNAME={username}
GOGUARD_PASSWORD={password}
GOGUARD_SUB_URL_TEMPLATE={sub_template}
GOGUARD_TIMEOUT_SECONDS=15

# ==========================================
# Database Configuration
# ==========================================
DATABASE_URL={db_url}

# ==========================================
# Payment (Card-to-Card) Configuration
# ==========================================
CARD_NUMBER={card_number}
CARD_HOLDER={card_holder}
CURRENCY_TITLE={currency_title}

# ==========================================
# Free Trial (Test Account) Configuration
# ==========================================
FREE_TRIAL_ENABLED={'true' if free_trial else 'false'}
FREE_TRIAL_TRAFFIC_GB={trial_traffic}
FREE_TRIAL_DURATION_DAYS={trial_days}

# ==========================================
# Referral Program Configuration
# ==========================================
REFERRAL_ENABLED={'true' if referral_enabled else 'false'}
REFERRAL_COMMISSION_PERCENT={ref_percent}

# ==========================================
# General & Localization
# ==========================================
DEFAULT_LANGUAGE=fa
DEBUG=false
"""

    with open(".env", "w", encoding="utf-8") as f:
        f.write(env_content)

    print(f"{GREEN}✓ Production configuration saved to .env successfully!{RESET}\n")

    # =========================================================================
    # Next Steps / Start Option
    # =========================================================================
    print(f"{BOLD}What would you like to do next?{RESET}")
    print("1) Launch with Docker Compose (docker compose up -d --build)")
    print("2) Launch with Python directly (python -m app.main)")
    print("3) Exit and launch manually later")

    choice = prompt_input("Enter choice [1/2/3]", default="3", required=False)

    if choice == "1":
        print(f"\n{CYAN}Starting Docker Compose...{RESET}")
        os.system("docker compose up -d --build")
    elif choice == "2":
        print(f"\n{CYAN}Starting GoGuard Bot directly...{RESET}")
        python_exec = sys.executable
        os.system(f'"{python_exec}" -m app.main')
    else:
        print(f"\n{GREEN}Setup completed successfully!{RESET}")
        print("To run the bot in Docker:")
        print(f"  {BOLD}docker compose up -d --build{RESET}")
        print("To run the bot directly with Python:")
        print(f"  {BOLD}python -m app.main{RESET}\n")


if __name__ == "__main__":
    main()
