#!/usr/bin/env python3
"""
Interactive Installation & Configuration Wizard for GoGuard Telegram Bot.
Collects and validates Bot Token, Admin IDs, GoGuard Credentials, and settings,
generating the production .env file and optionally starting the service.
"""

import getpass
import json
import os
import platform
import re
import shutil
import subprocess
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


def is_command_available(cmd: str) -> bool:
    """Check if an executable exists in system PATH."""
    return shutil.which(cmd) is not None


def is_docker_daemon_running() -> bool:
    """Verify if the Docker daemon is active and responding."""
    try:
        res = subprocess.run(
            "docker info",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return res.returncode == 0
    except Exception:
        return False


def get_docker_compose_cmd() -> str:
    """Determine whether 'docker compose' or 'docker-compose' is operational."""
    try:
        res = subprocess.run(
            "docker compose version",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if res.returncode == 0:
            return "docker compose"
    except Exception:
        pass

    try:
        res = subprocess.run(
            "docker-compose version",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if res.returncode == 0:
            return "docker-compose"
    except Exception:
        pass

    return ""


def install_docker_on_linux() -> bool:
    """
    Automatically installs Docker and the Docker Compose plugin on Linux
    using the official Docker installation script.
    """
    print(f"\n{CYAN}{BOLD}🐳 Docker is not installed on this system.{RESET}")
    print(f"{YELLOW}Automatically installing Docker and Docker Compose via official repository...{RESET}")

    # Ensure curl is available
    if not is_command_available("curl"):
        print("⏳ Installing curl...")
        if is_command_available("apt-get"):
            os.system("apt-get update -y && apt-get install -y curl")
        elif is_command_available("yum"):
            os.system("yum install -y curl")
        elif is_command_available("dnf"):
            os.system("dnf install -y curl")

    # Run official Docker convenience script
    print("⏳ Running official Docker installer (https://get.docker.com)...")
    res = os.system("curl -fsSL https://get.docker.com | sh")
    if res != 0 or not is_command_available("docker"):
        print(f"{RED}❌ Automatic Docker installation script failed (exit code {res}).{RESET}")
        return False

    # Start and enable Docker service
    print("⏳ Enabling and starting Docker daemon...")
    os.system("systemctl enable --now docker >/dev/null 2>&1 || service docker start >/dev/null 2>&1")

    # Add non-root user to docker group if applicable
    user = os.getenv("SUDO_USER") or os.getenv("USER")
    if user and user != "root":
        os.system(f"usermod -aG docker {user} >/dev/null 2>&1")

    print(f"{GREEN}✓ Docker installed and started successfully!{RESET}")
    return True


def ensure_docker_and_compose() -> tuple[bool, str]:
    """
    Ensures Docker and Docker Compose are installed and running.
    If missing on Linux, installs them automatically.
    Returns (success: bool, compose_command: str).
    """
    # 1. Install Docker if missing
    if not is_command_available("docker"):
        if sys.platform.startswith("linux"):
            if not install_docker_on_linux():
                return False, ""
        elif sys.platform == "win32":
            print(f"{RED}Docker is not installed or not running on Windows.{RESET}")
            if is_command_available("winget"):
                if prompt_yes_no("Would you like to install Docker Desktop using winget?", default=True):
                    print("⏳ Running winget install Docker.DockerDesktop...")
                    os.system("winget install Docker.DockerDesktop --accept-source-agreements --accept-package-agreements")
                    print(f"{YELLOW}Please launch Docker Desktop and run this setup again.{RESET}")
            return False, ""
        elif sys.platform == "darwin":
            print(f"{RED}Docker is not installed. Please install Docker Desktop for Mac.{RESET}")
            return False, ""
        else:
            print(f"{RED}Automatic Docker installation is not supported on this OS.{RESET}")
            return False, ""

    # 2. Check if Docker daemon is running
    if not is_docker_daemon_running():
        print("⏳ Docker service is stopped. Attempting to start daemon...")
        if sys.platform.startswith("linux"):
            os.system("systemctl start docker >/dev/null 2>&1 || service docker start >/dev/null 2>&1")
        if not is_docker_daemon_running():
            print(f"{RED}⚠️ Docker daemon is not active. Please start the Docker service (e.g., sudo systemctl start docker).{RESET}")
            return False, ""

    # 3. Check for Docker Compose
    compose_cmd = get_docker_compose_cmd()
    if not compose_cmd:
        print("⏳ Docker Compose plugin is missing. Installing docker-compose-plugin...")
        if sys.platform.startswith("linux"):
            if is_command_available("apt-get"):
                os.system("apt-get update -y && apt-get install -y docker-compose-plugin")
            elif is_command_available("yum"):
                os.system("yum install -y docker-compose-plugin")
            elif is_command_available("dnf"):
                os.system("dnf install -y docker-compose-plugin")

            compose_cmd = get_docker_compose_cmd()

            # Fallback to standalone docker-compose binary from GitHub releases
            if not compose_cmd:
                print("⏳ Downloading standalone docker-compose binary...")
                os.system(
                    "curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m) "
                    "-o /usr/local/bin/docker-compose && chmod +x /usr/local/bin/docker-compose"
                )
                compose_cmd = get_docker_compose_cmd()

        if not compose_cmd:
            print(f"{RED}❌ Docker Compose could not be configured automatically.{RESET}")
            return False, ""

    return True, compose_cmd


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


def detect_installation_state() -> dict:
    """Inspect system to determine if GoGuard Bot was previously installed and how."""
    has_env = os.path.exists(".env")
    has_data_db = os.path.exists("data/bot.db")
    has_root_db = os.path.exists("bot.db")
    has_db = has_data_db or has_root_db

    db_size = 0
    if has_data_db:
        db_size = os.path.getsize("data/bot.db")
    elif has_root_db:
        db_size = os.path.getsize("bot.db")
    db_size_str = f"{db_size / 1024:.1f} KB" if db_size else "Empty"

    docker_container = None
    docker_running = False
    if is_command_available("docker"):
        try:
            res = subprocess.run(
                'docker ps -a --filter "name=goguard_telegram_bot" --format "{{.Names}}|{{.Status}}"',
                shell=True,
                capture_output=True,
                text=True,
            )
            out = res.stdout.strip()
            if "goguard_telegram_bot" in out:
                docker_container = out
                docker_running = "Up" in out
        except Exception:
            pass

    systemd_service = False
    systemd_active = False
    if sys.platform.startswith("linux") and is_command_available("systemctl"):
        try:
            res = subprocess.run(
                "systemctl is-active goguard-bot",
                shell=True,
                capture_output=True,
                text=True,
            )
            if res.returncode == 0 and "active" in res.stdout:
                systemd_service = True
                systemd_active = True
            elif os.path.exists("/etc/systemd/system/goguard-bot.service"):
                systemd_service = True
        except Exception:
            pass

    if docker_container:
        mode_str = f"Docker Compose ({'Running ✅' if docker_running else 'Stopped ⏹️'})"
    elif systemd_service:
        mode_str = f"Systemd Service ({'Active ✅' if systemd_active else 'Inactive ⏹️'})"
    elif has_env and has_db:
        mode_str = "Python Standalone (Files Present)"
    elif has_env:
        mode_str = "Partially Configured (.env Present)"
    else:
        mode_str = "None (Fresh Installation)"

    is_installed = has_env or has_db or docker_container is not None or systemd_service

    return {
        "is_installed": is_installed,
        "mode_str": mode_str,
        "has_env": has_env,
        "has_db": has_db,
        "db_size_str": db_size_str,
        "docker_container": docker_container,
        "docker_running": docker_running,
        "systemd_service": systemd_service,
        "systemd_active": systemd_active,
    }


def sanitize_and_patch_env(existing: dict) -> dict:
    """Ensure .env has all required keys, fixed permissions, and safe formatting."""
    os.makedirs("data", exist_ok=True)
    if os.path.exists("bot.db") and not os.path.exists("data/bot.db"):
        try:
            shutil.copy2("bot.db", "data/bot.db")
            print(f"{GREEN}✓ Preserved existing bot.db into data/bot.db{RESET}")
        except Exception as exc:
            print(f"{YELLOW}Warning moving bot.db: {exc}{RESET}")

    if sys.platform.startswith("linux"):
        os.system("chmod -R 777 data >/dev/null 2>&1")

    # Sanitize ADMIN_IDS to JSON list
    admin_ids = existing.get("ADMIN_IDS", "[]")
    if not admin_ids.startswith("["):
        parts = [p.strip() for p in admin_ids.replace("'", "").replace('"', '').split(",") if p.strip()]
        admin_ids = "[" + ", ".join(parts) + "]"
        existing["ADMIN_IDS"] = admin_ids

    # Set DATABASE_URL to container path
    if existing.get("DATABASE_URL") in ("sqlite+aiosqlite:///bot.db", "sqlite+aiosqlite://bot.db"):
        existing["DATABASE_URL"] = "sqlite+aiosqlite:////app/data/bot.db"

    # Ensure WebUI variables
    if "WEB_ENABLE" not in existing:
        existing["WEB_ENABLE"] = "true"
    if "WEB_HOST" not in existing:
        existing["WEB_HOST"] = "0.0.0.0"
    if "WEB_PORT" not in existing:
        existing["WEB_PORT"] = "8080"
    if "WEB_USERNAME" not in existing:
        existing["WEB_USERNAME"] = "admin"
    if "WEB_PASSWORD" not in existing:
        existing["WEB_PASSWORD"] = "admin"
    if "WEB_SECRET_KEY" not in existing:
        import secrets
        existing["WEB_SECRET_KEY"] = secrets.token_hex(32)

    # Re-write .env keeping all existing variables
    lines = []
    written_keys = set()
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    k, _ = stripped.split("=", 1)
                    k = k.strip()
                    if k in existing:
                        lines.append(f"{k}={existing[k]}\n")
                        written_keys.add(k)
                    else:
                        lines.append(line)
                else:
                    lines.append(line)

    for k, v in existing.items():
        if k not in written_keys:
            lines.append(f"{k}={v}\n")

    with open(".env", "w", encoding="utf-8") as f:
        f.writelines(lines)

    return existing


def perform_code_update(state: dict, existing: dict) -> None:
    """Seamlessly updates repository code, rebuilds containers, preserving all data."""
    print(f"\n{BOLD}{CYAN}=== 🚀 Updating GoGuard Telegram Bot ==={RESET}")
    print(f"{CYAN}Preserving all database records, user balances, and configurations...{RESET}\n")

    # 1. Pull latest code if git repo
    if os.path.isdir(".git"):
        print("⏳ Pulling latest code from GitHub...")
        os.system("git stash >/dev/null 2>&1")
        pull_ret = os.system("git pull origin main")
        if pull_ret == 0:
            print(f"{GREEN}✓ Code updated to the latest commit from GitHub!{RESET}")
        else:
            print(f"{YELLOW}⚠️ Git pull finished (code {pull_ret}). Continuing with local files...{RESET}")

    # 2. Patch .env & ensure data permissions
    print("⏳ Verifying configuration and database directory permissions...")
    existing = sanitize_and_patch_env(existing)
    print(f"{GREEN}✓ Database preserved at data/bot.db with full 777 permissions.{RESET}")

    # 3. Determine restart mode
    use_docker = state["docker_container"] is not None or state["docker_running"]
    use_systemd = state["systemd_service"]

    if not use_docker and not use_systemd:
        print(f"\n{BOLD}Select launch mode for the update:{RESET}")
        print("1) Launch with Docker Compose (Recommended)")
        print("2) Launch with Python directly (python -m app.main)")
        ch = prompt_input("Enter choice [1/2]", default="1", required=False)
        use_docker = (ch == "1")

    if use_docker:
        print(f"\n{CYAN}🐳 Restarting container with Docker Compose...{RESET}")
        docker_ok, compose_cmd = ensure_docker_and_compose()
        if not docker_ok:
            print(f"{RED}❌ Docker is not ready. Aborting container restart.{RESET}")
            return

        print("⏳ Stopping previous container...")
        os.system(f"{compose_cmd} down >/dev/null 2>&1")

        print(f"⏳ Rebuilding and launching containers ({compose_cmd} up -d --build)...")
        build_ret = os.system(f"{compose_cmd} up -d --build")
        if build_ret == 0:
            print(f"\n{GREEN}{BOLD}══════════════════════════════════════════════════════════════════{RESET}")
            print(f"{GREEN}{BOLD}      🎉 GoGuard Telegram Bot Updated Successfully!               {RESET}")
            print(f"{GREEN}{BOLD}══════════════════════════════════════════════════════════════════{RESET}\n")
            print(f"• {BOLD}User Data:{RESET} 100% Preserved in data/bot.db (no data loss)")
            print(f"• {BOLD}Telegram Bot:{RESET} Running in background via Docker")
            print(f"• {BOLD}🌐 WebUI Management Panel:{RESET} http://<your-vps-ip>:8080")
            print(f"  Initial Credentials: Username: {BOLD}admin{RESET} | Password: {BOLD}admin{RESET}")
            print(f"  {YELLOW}⚠️ Note: You will be asked to set a new password on your first login!{RESET}")
            print(f"\nTo monitor real-time logs:")
            print(f"  {BOLD}{compose_cmd} logs -f{RESET}\n")
        else:
            print(f"{RED}❌ Docker build failed with code {build_ret}. Check docker logs above.{RESET}")

    elif use_systemd:
        print(f"\n{CYAN}⚙️ Updating Python environment and restarting systemd service...{RESET}")
        os.system("pip install -r requirements.txt")
        ret = os.system("systemctl restart goguard-bot")
        if ret == 0:
            print(f"{GREEN}✓ Service goguard-bot restarted successfully!{RESET}")
            print(f"🌐 WebUI Management Panel: http://<your-vps-ip>:8080")
            print(f"Logs: journalctl -u goguard-bot -f")
        else:
            print(f"{RED}❌ Failed to restart systemd service (exit code {ret}).{RESET}")

    else:
        print(f"\n{CYAN}📦 Installing updated Python packages in virtual environment...{RESET}")
        os.system("pip install -r requirements.txt")
        print(f"{GREEN}✓ Update ready! Launching bot...{RESET}\n")
        python_exec = sys.executable
        os.system(f'"{python_exec}" -m app.main')


def view_service_logs(state: dict) -> None:
    """Display real-time logs for Docker or Systemd."""
    print(f"\n{BOLD}{CYAN}=== 📊 Live Service Logs ==={RESET}\n")
    if is_command_available("docker"):
        compose_cmd = get_docker_compose_cmd() or "docker compose"
        os.system(f"{compose_cmd} ps")
        print("\nLast 30 container log lines:")
        os.system(f"{compose_cmd} logs --tail=30")
    elif sys.platform.startswith("linux") and state.get("systemd_service"):
        os.system("systemctl status goguard-bot --no-pager")
        os.system("journalctl -u goguard-bot -n 30 --no-pager")
    else:
        print(f"{YELLOW}No active container or systemd service detected.{RESET}")
    input(f"\n{BOLD}Press Enter to return to menu...{RESET}")


def main():
    clear_screen()
    print_banner()

    state = detect_installation_state()
    existing = load_existing_env()

    if state["is_installed"]:
        print(f"{CYAN}{BOLD}╔══════════════════════════════════════════════════════════════════╗{RESET}")
        print(f"{CYAN}{BOLD}║         🔍 Existing GoGuard Bot Installation Detected!           ║{RESET}")
        print(f"{CYAN}{BOLD}╚══════════════════════════════════════════════════════════════════╝{RESET}")
        print(f"• {BOLD}Deployment Status:{RESET} {state['mode_str']}")
        if state['has_db']:
            print(f"• {BOLD}Database File:{RESET} data/bot.db (Size: {state['db_size_str']}) -> {GREEN}Preserved & Safe{RESET}")
        if state['has_env']:
            print(f"• {BOLD}Configuration:{RESET} .env file found -> {GREEN}Preserved{RESET}")
        print(f"• {BOLD}WebUI Panel:{RESET} Port 8080 (Initial: admin / admin -> force password change)")
        print(f"──────────────────────────────────────────────────────────────────\n")

        print(f"{BOLD}What would you like to do?{RESET}")
        print(f"1) 🚀 {GREEN}{BOLD}Update Code & Restart{RESET} (Pull latest code, rebuild/restart, KEEP ALL DATA)")
        print(f"2) ⚙️  Reconfigure Settings (Interactively edit .env credentials)")
        print(f"3) 📊 Check Bot Status & View Logs")
        print(f"4) 🔄 Fresh Installation (Overwrite settings from scratch)")
        print(f"5) ❌ Exit\n")

        choice = prompt_input("Select an option [1/2/3/4/5]", default="1", required=False)

        if choice == "1":
            perform_code_update(state, existing)
            return
        elif choice == "3":
            view_service_logs(state)
            main()
            return
        elif choice == "5":
            print(f"\n{YELLOW}Exiting installer.{RESET}")
            sys.exit(0)
        elif choice == "4":
            if not prompt_yes_no("Are you sure you want to perform a fresh reinstall?", default=False):
                print(f"\n{YELLOW}Reinstallation cancelled.{RESET}")
                return
        # If choice == "2", continue with questionnaire with pre-filled defaults

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
    admin_ids_formatted = "[]"
    while True:
        default_admin = (
            existing.get("ADMIN_IDS", "")
            .replace("[", "")
            .replace("]", "")
            .replace(" ", "")
        )
        raw_admin_input = prompt_input(
            "Enter ADMIN_IDS (comma-separated Telegram User IDs, e.g. 123456789,987654321)",
            default=default_admin,
            required=True,
        )
        cleaned_input = raw_admin_input.replace("[", "").replace("]", "")
        parts = [p.strip() for p in cleaned_input.split(",") if p.strip()]
        if not parts or not all(p.lstrip("-").isdigit() for p in parts):
            print(f"{RED}⚠️ Invalid format. Please enter numeric user IDs separated by commas.{RESET}")
            continue
        admin_ids_formatted = "[" + ", ".join(parts) + "]"
        print(f"{GREEN}✓ Configured {len(parts)} admin ID(s): {admin_ids_formatted}{RESET}")
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
        default=existing.get("DATABASE_URL", "sqlite+aiosqlite:////app/data/bot.db"),
        required=False,
    )

    # WebUI Management Panel
    print(f"\n{CYAN}--- WebUI Management Panel Settings ---{RESET}")
    web_username = prompt_input(
        "WebUI Admin Username",
        default=existing.get("WEB_USERNAME", "admin"),
        required=False,
    )
    web_password = prompt_password(
        "WebUI Admin Password",
        default=existing.get("WEB_PASSWORD", "admin"),
        required=False,
    )
    import secrets
    web_secret = existing.get("WEB_SECRET_KEY") or secrets.token_hex(32)

    # =========================================================================
    # Save .env File
    # =========================================================================
    print(f"\n{BOLD}{CYAN}=== Saving Configuration ==={RESET}")

    env_content = f"""# ==========================================
# Telegram Bot Configuration
# ==========================================
BOT_TOKEN={bot_token}
ADMIN_IDS={admin_ids_formatted}
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
# Web Management Panel (FastAPI WebUI)
# ==========================================
WEB_ENABLE=true
WEB_HOST=0.0.0.0
WEB_PORT=8080
WEB_USERNAME={web_username}
WEB_PASSWORD={web_password}
WEB_SECRET_KEY={web_secret}

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
    print(f"{CYAN}🌐 WebUI Panel will run on: {BOLD}http://<your-server-ip>:8080{RESET}")
    print(f"   Credentials: Username: {BOLD}{web_username}{RESET} / Password: (hidden)")
    print(f"   {YELLOW}⚠️ Note: On your first login (admin/admin), you will be asked to set a new password.{RESET}\n")

    # =========================================================================
    # Next Steps / Start Option
    # =========================================================================
    print(f"{BOLD}What would you like to do next?{RESET}")
    print("1) Launch with Docker Compose (docker compose up -d --build)")
    print("2) Launch with Python directly (python -m app.main)")
    print("3) Exit and launch manually later")

    choice = prompt_input("Enter choice [1/2/3]", default="3", required=False)

    if choice == "1":
        docker_ready, compose_cmd = ensure_docker_and_compose()
        if docker_ready and compose_cmd:
            os.makedirs("data", exist_ok=True)
            if sys.platform.startswith("linux"):
                os.system("chmod -R 777 data >/dev/null 2>&1")
            print(f"\n{CYAN}Starting containers with {BOLD}{compose_cmd} up -d --build{RESET}...{RESET}")
            ret = os.system(f"{compose_cmd} up -d --build")
            if ret == 0:
                print(f"\n{GREEN}✅ GoGuard Telegram Bot container started successfully!{RESET}")
                print(f"To monitor logs in real-time:")
                print(f"  {BOLD}{compose_cmd} logs -f{RESET}\n")
            else:
                print(f"\n{RED}❌ Failed to start containers (exit code {ret}). Check the logs above.{RESET}\n")
        else:
            print(f"\n{YELLOW}Docker is not ready. You can run the bot directly with Python:{RESET}")
            print(f"  {BOLD}python -m app.main{RESET}\n")
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
