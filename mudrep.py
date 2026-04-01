#!/usr/bin/env python3
"""
mudrep.py - Mudrep CLI Tool v2.0.0
Educational Purpose Only.
"""

import os
import sys
import re
import subprocess
import sqlite3
import socket
import time
import threading
import hashlib
import json
import asyncio
import logging
import getpass
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

VERSION      = "2.0.0"
PROGRAM_NAME = "mudrep"
DB_FILE      = "tasks.db"
TASK_DIR     = "tasks"
CONFIG_FILE  = "remote_config.json"
USERS_FILE   = "mudrep_users.json"

os.makedirs(TASK_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Global State
# ─────────────────────────────────────────────────────────────────────────────

stop_flag                = False
remote_mode_active       = False
telegram_app             = None
authorized_user_id       = None
bot_thread               = None
bot_event_loop: Optional[asyncio.AbstractEventLoop] = None
internet_watchdog_threads: List[threading.Thread] = []
current_user: Optional[str] = None

# ─────────────────────────────────────────────────────────────────────────────
# ANSI Color Helpers
# ─────────────────────────────────────────────────────────────────────────────

C_PRIMARY = "\033[38;2;255;127;80m"
C_WHITE   = "\033[97m"
C_RESET   = "\033[0m"

def print_primary(text: str):
    print(f"{C_PRIMARY}{text}{C_RESET}")

def print_label_value(label: str, value: str):
    print(f"{C_PRIMARY}{label}{C_WHITE}{value}{C_RESET}")

def print_error(msg: str):
    print(f"{C_PRIMARY}Error: {C_WHITE}{msg}{C_RESET}")

# ─────────────────────────────────────────────────────────────────────────────
# Authentication System
# ─────────────────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def load_users() -> dict:
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_users(users: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def register_user() -> Optional[str]:
    """First-time account creation. Returns the new username."""
    print(f"\n{C_PRIMARY}=== Welcome to {PROGRAM_NAME} - First Time Setup ==={C_RESET}")
    print(f"{C_WHITE}No accounts found. Please create your account.{C_RESET}\n")

    while True:
        username = input(f"{C_PRIMARY}Create username: {C_RESET}").strip()
        if not username:
            print_error("Username cannot be empty.")
            continue
        if len(username) < 3:
            print_error("Username must be at least 3 characters.")
            continue
        break

    while True:
        password = getpass.getpass(f"{C_PRIMARY}Create password: {C_RESET}")
        if not password:
            print_error("Password cannot be empty.")
            continue
        if len(password) < 4:
            print_error("Password must be at least 4 characters.")
            continue
        confirm = getpass.getpass(f"{C_PRIMARY}Confirm password: {C_RESET}")
        if password != confirm:
            print_error("Passwords do not match.")
            continue
        break

    users = load_users()
    users[username] = {
        "password_hash": hash_password(password),
        "created_at": datetime.now().isoformat(),
    }
    save_users(users)
    print(f"\n{C_PRIMARY}Account created successfully. Welcome, {C_WHITE}{username}{C_RESET}\n")
    return username

def login() -> Optional[str]:
    """
    Login prompt shown every time the program starts.
    If no users exist, triggers registration first.
    Returns the authenticated username, or None after 3 failed attempts.
    """
    users = load_users()
    if not users:
        return register_user()

    print(f"\n{C_PRIMARY}=== {PROGRAM_NAME} Login ==={C_RESET}")

    for attempt in range(3):
        username = input(f"{C_PRIMARY}Username: {C_RESET}").strip()
        password = getpass.getpass(f"{C_PRIMARY}Password: {C_RESET}")

        if username in users and users[username]["password_hash"] == hash_password(password):
            print(f"\n{C_PRIMARY}Login successful. Welcome, {C_WHITE}{username}{C_RESET}")
            return username

        remaining = 2 - attempt
        if remaining > 0:
            print(f"{C_PRIMARY}Invalid credentials. {remaining} attempt(s) remaining.{C_RESET}")
        else:
            print(f"{C_PRIMARY}Access denied.{C_RESET}")

    return None

# ─────────────────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT UNIQUE,
            file          TEXT,
            trigger_type  TEXT,
            trigger_value TEXT,
            created_at    TEXT
        )
    """)
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# Internet Check
# ─────────────────────────────────────────────────────────────────────────────

def has_internet() -> bool:
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────────────────────
# UI Renderer
# ─────────────────────────────────────────────────────────────────────────────

def display_interface(username: str):
    os.system("clear" if sys.platform != "win32" else "cls")
    print(f"\n{C_PRIMARY}# {PROGRAM_NAME} v{VERSION}{C_RESET}")
    print()
    print(f"{C_PRIMARY}## System{C_RESET}")
    print_label_value("- User:    ", username)
    print_label_value("- Host:    ", PROGRAM_NAME)
    print_label_value("- Shell:   ", "/bin/bash")
    print_label_value("- Root:    ", f"/users/{username}/code/apps")
    print()
    print_primary("---")
    print()
    print(f"{C_PRIMARY}## Main commands{C_RESET}")
    print(f"{C_PRIMARY}record   {C_WHITE}store commands{C_RESET}")
    print(f"{C_PRIMARY}inject   {C_WHITE}run commands{C_RESET}")
    print(f"{C_PRIMARY}remote   {C_WHITE}access terminal from telegram bot{C_RESET}")
    print(f"{C_PRIMARY}list     {C_WHITE}shows all tasks{C_RESET}")
    print(f"{C_PRIMARY}exit     {C_WHITE}quit from terminal{C_RESET}")
    print()
    print_primary("---")
    print()
    print(f"{C_PRIMARY}## Sub commands{C_RESET}")
    print(f"{C_PRIMARY}- {C_WHITE}del <filename>   delete a task{C_RESET}")
    print(f"{C_PRIMARY}- {C_WHITE}cat <filename>   view task content{C_RESET}")
    print(f"{C_PRIMARY}- {C_WHITE}help             full command list{C_RESET}")
    print()
    print_primary("---")
    print()
    print(f"{C_PRIMARY}Warning {username}!{C_RESET}")
    print(f"{C_WHITE}This is a Tool For Educational Purpose Only{C_RESET}")
    print(f"{C_WHITE}Don't use For Harmful Purpose This May Cause End Up in Jail.{C_RESET}")
    print()
    print_primary("---")
    print()

def display_prompt(username: str, path: str) -> str:
    top = (
        f"{C_PRIMARY}+--({C_WHITE}{username}{C_PRIMARY}@{PROGRAM_NAME})-"
        f"[{C_WHITE}{path}{C_PRIMARY}]{C_RESET}"
    )
    print(top)
    return input(f"{C_PRIMARY}+--${C_RESET} ")

# ─────────────────────────────────────────────────────────────────────────────
# Path Manager
# ─────────────────────────────────────────────────────────────────────────────

class PathManager:
    def __init__(self):
        self.home = str(Path.home())
        desktop = os.path.join(self.home, "Desktop")
        if os.path.isdir(desktop):
            self.current_path = "~/Desktop"
            try:
                os.chdir(desktop)
            except Exception:
                self.current_path = "~"
                os.chdir(self.home)
        else:
            self.current_path = "~"
            os.chdir(self.home)

    def _resolve(self, path: str) -> str:
        if path == "~":
            return self.home
        if path.startswith("~/"):
            return os.path.join(self.home, path[2:])
        return path

    def _display(self, abs_path: str) -> str:
        abs_path = os.path.realpath(abs_path)
        if abs_path == self.home:
            return "~"
        if abs_path.startswith(self.home + os.sep):
            return "~/" + os.path.relpath(abs_path, self.home)
        return abs_path

    def change(self, new_path: str) -> Tuple[bool, str]:
        try:
            if not new_path or new_path == "~":
                resolved = self.home
            elif new_path == "..":
                current_abs = self._resolve(self.current_path)
                resolved = os.path.dirname(os.path.realpath(current_abs))
            elif new_path.startswith("/"):
                resolved = new_path
            elif new_path.startswith("~/"):
                resolved = os.path.join(self.home, new_path[2:])
            else:
                current_abs = self._resolve(self.current_path)
                resolved = os.path.join(os.path.realpath(current_abs), new_path)

            resolved = os.path.realpath(resolved)
            if os.path.isdir(resolved):
                os.chdir(resolved)
                self.current_path = self._display(resolved)
                return True, self.current_path
            return False, f"Directory not found: {new_path}"
        except Exception as e:
            return False, str(e)

    def sync(self):
        """Sync display path with actual cwd after shell commands."""
        cwd = os.path.realpath(os.getcwd())
        self.current_path = self._display(cwd)

# ─────────────────────────────────────────────────────────────────────────────
# Shell Command Executors
# ─────────────────────────────────────────────────────────────────────────────

def execute_direct_command(command: str) -> Optional[str]:
    """Execute a shell command for the CLI. Returns output string or None."""
    try:
        if command.lower() in ("clear", "cls"):
            return "CLEAR"
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        if result.stdout:
            return result.stdout.rstrip()
        if result.stderr and result.returncode != 0:
            return f"Error: {result.stderr.rstrip()}"
        if result.returncode == 0:
            return "Command executed successfully (no output)"
        return f"Command failed with exit code {result.returncode}"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out (30s)"
    except Exception as e:
        return f"Error: {str(e)}"

def execute_shell_command(cmd: str) -> str:
    """Execute a shell command and return output string (used by Telegram /shell)."""
    try:
        if cmd.startswith("cd "):
            path = cmd[3:].strip()
            if path == "~":
                path = os.path.expanduser("~")
            os.chdir(path)
            return f"Changed to: {os.getcwd()}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            if result.returncode != 0:
                output += f"\nError: {result.stderr}"
            else:
                output += result.stderr
        return output.strip() if output.strip() else "Command executed (no output)"
    except subprocess.TimeoutExpired:
        return "Command timeout (30s)"
    except Exception as e:
        return f"Error: {str(e)}"

# ─────────────────────────────────────────────────────────────────────────────
# Task Name Validation
# ─────────────────────────────────────────────────────────────────────────────

_VALID_NAME = re.compile(r'^[a-zA-Z0-9_\-]+$')

def is_valid_task_name(name: str) -> bool:
    return bool(_VALID_NAME.match(name)) and 1 <= len(name) <= 64

# ─────────────────────────────────────────────────────────────────────────────
# Task: Core Helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_commands(file_path: str) -> List[str]:
    with open(file_path) as f:
        return [line.strip() for line in f if line.strip()]

def run_commands(commands: List[str], internet_mode: bool = False, task_name: str = ""):
    """Execute a list of commands, printing output to console."""
    global stop_flag
    for cmd in commands:
        if stop_flag:
            print(f"Task '{task_name}' stopped.")
            return
        if internet_mode and not has_internet():
            print(f"Internet lost. Kill switch activated for task '{task_name}'.")
            return
        print(f"[{task_name}] > {cmd}")
        try:
            if cmd.startswith("cd "):
                os.chdir(cmd[3:].strip())
            else:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                if result.stdout:
                    print(result.stdout)
                if result.stderr:
                    if result.returncode != 0:
                        print("Error:", result.stderr)
                    else:
                        print(result.stderr)
        except subprocess.TimeoutExpired:
            print(f"Command timeout: {cmd}")
        except Exception as e:
            print(f"Error executing '{cmd}': {e}")

def run_commands_with_output(
    commands: List[str],
    internet_mode: bool = False,
    task_name: str = "",
) -> List[str]:
    """Execute commands, collect and return all output as a list of strings."""
    global stop_flag
    output_lines: List[str] = []

    for cmd in commands:
        if stop_flag:
            output_lines.append(f"Task '{task_name}' stopped.")
            break
        if internet_mode and not has_internet():
            output_lines.append(f"Internet lost. Kill switch activated for task '{task_name}'.")
            return output_lines

        output_lines.append(f"[{task_name}] > {cmd}")

        try:
            if cmd.startswith("cd "):
                os.chdir(cmd[3:].strip())
                output_lines.append(f"Changed directory to: {os.getcwd()}")
            else:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                if result.stdout:
                    output_lines.append(result.stdout.rstrip())
                if result.stderr:
                    if result.returncode != 0:
                        output_lines.append(f"Error: {result.stderr.rstrip()}")
                    else:
                        output_lines.append(result.stderr.rstrip())
        except subprocess.TimeoutExpired:
            output_lines.append(f"Command timeout: {cmd}")
        except Exception as e:
            output_lines.append(f"Error executing '{cmd}': {e}")

    return output_lines

def internet_loop(commands: List[str], task_name: str):
    """Background thread: wait for internet, then run task."""
    global stop_flag
    while not stop_flag:
        if has_internet():
            print(f"Internet detected! Executing task '{task_name}'...")
            run_commands(commands, internet_mode=True, task_name=task_name)
            break
        time.sleep(5)
    print(f"Internet watchdog for task '{task_name}' finished.")

# ─────────────────────────────────────────────────────────────────────────────
# Task: record
# ─────────────────────────────────────────────────────────────────────────────

def record_task(name: str):
    if not is_valid_task_name(name):
        print_error(
            "Invalid task name. Use only letters, numbers, underscores, or hyphens (max 64 chars)."
        )
        return

    commands: List[str] = []

    print(f"\n{C_PRIMARY}[RECORD MODE]{C_RESET} {C_WHITE}Type commands one by one. Type 'exit' to finish.{C_RESET}")
    print(f"{C_WHITE}You can use any shell command.{C_RESET}")
    print(f"{C_PRIMARY}" + "-" * 40 + C_RESET)

    while True:
        try:
            cmd = input(f"{C_PRIMARY}record> {C_RESET}").strip()
            if cmd == "exit":
                break
            if cmd:
                commands.append(cmd)
                print(f"{C_PRIMARY}  + Added: {C_WHITE}{cmd}{C_RESET}")
        except KeyboardInterrupt:
            print("\nRecording cancelled.")
            return

    if not commands:
        print_primary("No commands recorded.")
        return

    print(f"\n{C_PRIMARY}Trigger Types:{C_RESET}")
    print(f"{C_PRIMARY}  1. {C_WHITE}none     (run immediately){C_RESET}")
    print(f"{C_PRIMARY}  2. {C_WHITE}internet (run when internet available){C_RESET}")
    print(f"{C_PRIMARY}  3. {C_WHITE}datetime (run at a specific date/time){C_RESET}")

    choice = input(f"{C_PRIMARY}Choose trigger (1/2/3): {C_RESET}").strip()

    if choice in ("1", ""):
        trigger_type  = "none"
        trigger_value = ""
    elif choice == "2":
        trigger_type  = "internet"
        trigger_value = "loop"
    elif choice == "3":
        while True:
            trigger_value = input(
                f"{C_PRIMARY}Enter datetime (YYYY-MM-DD HH:MM): {C_RESET}"
            ).strip()
            try:
                datetime.strptime(trigger_value, "%Y-%m-%d %H:%M")
                break
            except ValueError:
                print_error("Invalid format. Use YYYY-MM-DD HH:MM  (e.g. 2025-12-31 09:00)")
        trigger_type = "datetime"
    else:
        print_error("Invalid trigger selection.")
        return

    file_path = os.path.join(TASK_DIR, f"{name}.txt")
    with open(file_path, "w") as f:
        for c in commands:
            f.write(c + "\n")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO tasks"
        " (name, file, trigger_type, trigger_value, created_at) VALUES (?,?,?,?,?)",
        (name, file_path, trigger_type, trigger_value, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    print(f"\n{C_PRIMARY}[OK] Task '{C_WHITE}{name}{C_PRIMARY}' saved "
          f"with {C_WHITE}{len(commands)}{C_PRIMARY} command(s).{C_RESET}")
    print(f"{C_PRIMARY}     File:    {C_WHITE}{file_path}{C_RESET}")
    print(f"{C_PRIMARY}     Trigger: {C_WHITE}{trigger_type}{C_RESET}")

# ─────────────────────────────────────────────────────────────────────────────
# Task: inject (CLI)
# ─────────────────────────────────────────────────────────────────────────────

def inject_task(name: str):
    global stop_flag, internet_watchdog_threads

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT file, trigger_type, trigger_value FROM tasks WHERE name=?", (name,))
    row = c.fetchone()
    conn.close()

    if not row:
        print_error(f"Task '{name}' not found.")
        return

    file_path, trigger_type, trigger_value = row

    if not os.path.exists(file_path):
        print_error(f"Task file missing for '{name}'.")
        return

    commands = load_commands(file_path)

    print(f"\n{C_PRIMARY}--- Executing Task: {C_WHITE}{name}{C_PRIMARY} ---{C_RESET}")
    print(f"{C_PRIMARY}Commands: {C_WHITE}{len(commands)}{C_RESET}")
    print(f"{C_PRIMARY}Trigger:  {C_WHITE}{trigger_type}{C_RESET}")
    print(f"{C_PRIMARY}" + "-" * 30 + C_RESET)

    if trigger_type == "none":
        run_commands(commands, task_name=name)

    elif trigger_type == "internet":
        t = threading.Thread(target=internet_loop, args=(commands, name), daemon=True)
        t.start()
        internet_watchdog_threads.append(t)
        print(f"{C_PRIMARY}Internet watchdog started for task '{name}'.{C_RESET}")

    elif trigger_type == "datetime":
        try:
            target = datetime.strptime(trigger_value, "%Y-%m-%d %H:%M")
            print(f"{C_PRIMARY}Waiting until: {C_WHITE}{target}{C_RESET}")
            while datetime.now() < target and not stop_flag:
                time.sleep(5)
            if not stop_flag:
                print(f"{C_PRIMARY}Time reached! Executing commands...{C_RESET}")
                run_commands(commands, task_name=name)
            else:
                print(f"{C_PRIMARY}Task '{name}' cancelled.{C_RESET}")
        except ValueError:
            print_error(f"Invalid datetime format stored: {trigger_value}")

# ─────────────────────────────────────────────────────────────────────────────
# Task: list
# ─────────────────────────────────────────────────────────────────────────────

def list_tasks() -> list:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT name, trigger_type, trigger_value, created_at FROM tasks ORDER BY created_at DESC"
    )
    rows = c.fetchall()
    conn.close()

    if not rows:
        print_primary("\nNo tasks found.")
        return []

    print(f"\n{C_PRIMARY}" + "=" * 80 + C_RESET)
    print(f"{C_PRIMARY}{'Task Name':<20} {'Trigger':<12} {'Value':<30} {'Created':<18}{C_RESET}")
    print(f"{C_PRIMARY}" + "=" * 80 + C_RESET)
    for name, trigger_type, trigger_value, created_at in rows:
        created_short = (created_at or "N/A")[:16]
        val_display   = (trigger_value or "-")[:30]
        print(f"{C_WHITE}{name:<20} {trigger_type:<12} {val_display:<30} {created_short:<18}{C_RESET}")
    print(f"{C_PRIMARY}" + "=" * 80 + C_RESET)
    print(f"{C_PRIMARY}Total: {C_WHITE}{len(rows)}{C_PRIMARY} task(s){C_RESET}")
    return rows

# ─────────────────────────────────────────────────────────────────────────────
# Task: cat
# ─────────────────────────────────────────────────────────────────────────────

def cat_task(name: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT file, trigger_type, trigger_value, created_at FROM tasks WHERE name=?", (name,)
    )
    row = c.fetchone()
    conn.close()

    if not row:
        print_error(f"Task '{name}' not found.")
        return

    file_path, trigger_type, trigger_value, created_at = row

    if not os.path.exists(file_path):
        print_error(f"Task file missing: {file_path}")
        return

    sep = f"{C_PRIMARY}" + "=" * 60 + C_RESET
    print(f"\n{sep}")
    print_label_value("Task:    ", name)
    print_label_value("Trigger: ", trigger_type)
    print_label_value("Value:   ", trigger_value or "-")
    print_label_value("Created: ", created_at or "N/A")
    print(sep)
    with open(file_path) as f:
        print(f"{C_WHITE}{f.read()}{C_RESET}")
    print(sep)

# ─────────────────────────────────────────────────────────────────────────────
# Task: delete
# Returns True if deleted, False if not found
# ─────────────────────────────────────────────────────────────────────────────

def delete_task(name: str) -> bool:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT file FROM tasks WHERE name=?", (name,))
    row = c.fetchone()

    if not row:
        conn.close()
        return False

    file_path = row[0]
    if os.path.exists(file_path):
        os.remove(file_path)

    c.execute("DELETE FROM tasks WHERE name=?", (name,))
    conn.commit()
    conn.close()
    print(f"{C_PRIMARY}[OK] Task '{C_WHITE}{name}{C_PRIMARY}' deleted.{C_RESET}")
    return True

# ─────────────────────────────────────────────────────────────────────────────
# Remote Config
# ─────────────────────────────────────────────────────────────────────────────

def save_remote_config(password_hash: str, bot_token: str):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"password_hash": password_hash, "bot_token": bot_token}, f)

def load_remote_config() -> Optional[dict]:
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return None

def remove_remote_config():
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)
        return True
    return False

def view_remote_config():
    """View current remote configuration (masked)"""
    config = load_remote_config()
    if not config:
        print_primary("\nNo remote configuration found.")
        return False
    
    token = config["bot_token"]
    masked = token[:20] + "..." + token[-10:] if len(token) > 30 else token
    print(f"\n{C_PRIMARY}Current Remote Configuration:{C_RESET}")
    print_label_value("Bot Token: ", masked)
    print_label_value("Password:  ", "******** (hashed)")
    print(f"{C_PRIMARY}Config file: {C_WHITE}{CONFIG_FILE}{C_RESET}")
    return True

# ─────────────────────────────────────────────────────────────────────────────
# Remote Setup with Remove Option
# ─────────────────────────────────────────────────────────────────────────────

def setup_remote_mode():
    """Configure remote control via Telegram bot with option to remove existing"""
    sep = f"{C_PRIMARY}" + "=" * 60 + C_RESET
    print(f"\n{sep}")
    print(f"{C_PRIMARY}TELEGRAM BOT REMOTE SETUP{C_RESET}")
    print(sep)

    config = load_remote_config()
    if config:
        print(f"\n{C_PRIMARY}Remote configuration already exists!{C_RESET}")
        print(f"\n{C_PRIMARY}Options:{C_RESET}")
        print(f"{C_PRIMARY}  1. {C_WHITE}Keep existing configuration{C_RESET}")
        print(f"{C_PRIMARY}  2. {C_WHITE}Remove existing configuration{C_RESET}")
        print(f"{C_PRIMARY}  3. {C_WHITE}View current configuration{C_RESET}")
        print(f"{C_PRIMARY}  4. {C_WHITE}Remove and create new configuration{C_RESET}")
        
        choice = input(f"\n{C_PRIMARY}Enter choice (1-4): {C_RESET}").strip()

        if choice == "1":
            print_primary("Keeping existing configuration.")
            print(f"{C_PRIMARY}To start remote mode, type: {C_WHITE}remote{C_RESET}")
            return
        elif choice == "2":
            if remove_remote_config():
                print_primary("Remote configuration removed successfully.")
                print(f"{C_PRIMARY}Run 'remote_setup' again to create new configuration.{C_RESET}")
            else:
                print_error("Failed to remove configuration.")
            return
        elif choice == "3":
            view_remote_config()
            return
        elif choice == "4":
            remove_remote_config()
            print_primary("Existing configuration removed. Proceeding with setup...")
        else:
            print_error("Invalid choice. Keeping existing configuration.")
            return

    print(f"\n{C_PRIMARY}STEP 1: BOT TOKEN{C_RESET}")
    print(f"{C_WHITE}  1. Open Telegram and search for @BotFather{C_RESET}")
    print(f"{C_WHITE}  2. Send /newbot and follow the instructions{C_RESET}")
    print(f"{C_WHITE}  3. Copy the token BotFather gives you{C_RESET}")
    print(f"{C_PRIMARY}  Token format: 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz{C_RESET}")

    while True:
        bot_token = input(f"\n{C_PRIMARY}Enter bot token: {C_RESET}").strip()
        if not bot_token:
            print_error("Token cannot be empty.")
            continue
        if ":" not in bot_token or len(bot_token) < 30:
            print_error("Invalid token format. Check and try again.")
            continue
        break

    print(f"\n{C_PRIMARY}STEP 2: SET REMOTE ACCESS PASSWORD{C_RESET}")
    print(f"{C_WHITE}  This password is required when connecting via Telegram.{C_RESET}")

    while True:
        password = getpass.getpass(f"{C_PRIMARY}Enter password: {C_RESET}")
        if not password or len(password) < 4:
            print_error("Password must be at least 4 characters.")
            continue
        confirm = getpass.getpass(f"{C_PRIMARY}Confirm password: {C_RESET}")
        if password != confirm:
            print_error("Passwords do not match.")
            continue
        break

    save_remote_config(hash_password(password), bot_token)

    print(f"\n{sep}")
    print(f"{C_PRIMARY}REMOTE CONFIGURATION SAVED!{C_RESET}")
    print(sep)
    print(f"\n{C_PRIMARY}Next steps:{C_RESET}")
    print(f"{C_WHITE}  1. Type 'remote' to start the bot{C_RESET}")
    print(f"{C_WHITE}  2. Open Telegram and send /start to your bot{C_RESET}")
    print(f"{C_WHITE}  3. Enter the password to authenticate{C_RESET}")
    print(f"\n{C_PRIMARY}Telegram commands available:{C_RESET}")
    print(f"{C_WHITE}  /list  /record  /inject  /cat  /del{C_RESET}")
    print(f"{C_WHITE}  /shell  /cd  /pwd  /ls  /stop  /help{C_RESET}\n")

# ─────────────────────────────────────────────────────────────────────────────
# Remote Start
# ─────────────────────────────────────────────────────────────────────────────

def start_remote_mode():
    global remote_mode_active, bot_thread, authorized_user_id

    config = load_remote_config()
    if not config:
        print_primary("\nNo remote configuration found.")
        print(f"{C_WHITE}Run 'remote_setup' first to configure the bot.{C_RESET}")
        return

    sep = f"{C_PRIMARY}" + "=" * 60 + C_RESET
    print(f"\n{sep}")
    print(f"{C_PRIMARY}STARTING REMOTE CONTROL MODE{C_RESET}")
    print(sep)

    password = getpass.getpass(f"\n{C_PRIMARY}Enter remote access password: {C_RESET}")
    if hash_password(password) != config["password_hash"]:
        print_error("Invalid password.")
        return

    bot_token = config["bot_token"]

    # Silence all Telegram / HTTP library logs
    for logger_name in ("telegram", "httpx", "httpcore", "asyncio", "urllib3"):
        logging.getLogger(logger_name).setLevel(logging.CRITICAL)

    remote_mode_active = True
    authorized_user_id = None

    def run_bot():
        global remote_mode_active
        try:
            run_telegram_bot(bot_token)
        except Exception:
            remote_mode_active = False

    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    time.sleep(2)

    print(f"\n{C_PRIMARY}Bot is running silently in the background.{C_RESET}")
    print(f"{C_WHITE}Open Telegram and send /start to your bot.{C_RESET}")
    print(f"{C_PRIMARY}Type 'exit' to stop remote mode and return to the shell.{C_RESET}\n")

    def _watch_input():
        global remote_mode_active, authorized_user_id
        while remote_mode_active:
            try:
                cmd = input()
                if cmd.strip().lower() in ("exit", "quit"):
                    print_primary("\nStopping remote mode...")
                    remote_mode_active = False
                    authorized_user_id = None
                    break
            except (EOFError, KeyboardInterrupt):
                remote_mode_active = False
                authorized_user_id = None
                break

    input_thread = threading.Thread(target=_watch_input, daemon=True)
    input_thread.start()

    while remote_mode_active:
        time.sleep(0.5)

    print_primary("Remote mode stopped.\n")

def remote_command():
    """'remote' command: auto-setup if no config exists, then start."""
    config = load_remote_config()
    if not config:
        print_primary("No remote configuration found. Starting setup first...\n")
        setup_remote_mode()
        config = load_remote_config()
        if not config:
            return
    start_remote_mode()

# ─────────────────────────────────────────────────────────────────────────────
# Telegram Bot Helpers
# ─────────────────────────────────────────────────────────────────────────────

def is_authorized(update: Update) -> bool:
    return remote_mode_active and authorized_user_id == update.effective_user.id

def _tg_send(coro) -> None:
    """Schedule an async coroutine on the bot's event loop from any worker thread."""
    if bot_event_loop is None or bot_event_loop.is_closed():
        return
    future = asyncio.run_coroutine_threadsafe(coro, bot_event_loop)
    try:
        future.result(timeout=30)
    except Exception:
        pass

def _get_command_name(text: str) -> str:
    """Extract the bare command from message text, stripping @botname suffix."""
    word = text.strip().split()[0] if text.strip() else ""
    return word.split("@")[0]

def _send_output_chunks(update: Update, output_lines: List[str], task_name: str):
    """Send task output to Telegram, splitting into chunks if > 4000 chars."""
    full = "\n".join(output_lines)
    if not full.strip():
        _tg_send(update.message.reply_text("Task completed with no output."))
        return
    if len(full) > 4000:
        chunks = [full[i : i + 4000] for i in range(0, len(full), 4000)]
        for idx, chunk in enumerate(chunks):
            _tg_send(update.message.reply_text(f"Output ({idx+1}/{len(chunks)}):\n{chunk}"))
    else:
        _tg_send(update.message.reply_text(f"Output:\n{full}"))

# ─────────────────────────────────────────────────────────────────────────────
# Telegram: /start
# ─────────────────────────────────────────────────────────────────────────────

async def tg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global authorized_user_id
    if not remote_mode_active:
        await update.message.reply_text("Remote mode is not active on the server.")
        return
    if authorized_user_id is None:
        context.user_data["awaiting_auth"] = True
        await update.message.reply_text(
            "AUTHENTICATION REQUIRED\n\n"
            "This bot is password protected.\n"
            "Please send your remote access password."
        )
        return
    await update.message.reply_text(
        f"WELCOME TO {PROGRAM_NAME.upper()} BOT\n\n"
        "Available commands:\n"
        "/list              - Show all tasks\n"
        "/record <name>     - Record a new task\n"
        "/inject <name>     - Execute a task\n"
        "/cat <name>        - View task content\n"
        "/del <name>        - Delete a task\n"
        "/shell <command>   - Run a shell command\n"
        "/cd <directory>    - Change directory\n"
        "/pwd               - Show current directory\n"
        "/ls                - List files in current directory\n"
        "/stop              - Stop remote mode\n"
        "/help              - Show this help"
    )

# ─────────────────────────────────────────────────────────────────────────────
# Telegram: Authentication
# ─────────────────────────────────────────────────────────────────────────────

async def tg_handle_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global authorized_user_id
    if not context.user_data.get("awaiting_auth", False):
        return
    password = update.message.text.strip()
    config = load_remote_config()
    if config and hash_password(password) == config["password_hash"]:
        authorized_user_id = update.effective_user.id
        context.user_data.clear()
        await update.message.reply_text(
            "AUTHENTICATION SUCCESSFUL!\n\n"
            "You are now authorized.\n"
            "Send /start to see available commands."
        )
    else:
        await update.message.reply_text(
            "Invalid password. Please try again.\n"
            "(Send /start to cancel and restart authentication.)"
        )

# ─────────────────────────────────────────────────────────────────────────────
# Telegram: /list
# ─────────────────────────────────────────────────────────────────────────────

async def tg_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name, trigger_type, trigger_value FROM tasks")
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        await update.message.reply_text("No tasks found.")
        return
    
    msg = "YOUR TASKS:\n\n"
    for name, trigger_type, trigger_value in rows:
        msg += f"- {name}\n"
        msg += f"  Trigger: {trigger_type}\n"
        if trigger_value:
            msg += f"  Value:   {trigger_value}\n"
        msg += "\n"
    
    if len(msg) > 4000:
        msg = msg[:4000] + "\n... (truncated)"
    
    await update.message.reply_text(msg)

# ─────────────────────────────────────────────────────────────────────────────
# Telegram: /record
# ─────────────────────────────────────────────────────────────────────────────

async def tg_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    
    # Check if we have arguments
    if not context.args:
        await update.message.reply_text(
            "Usage: /record <taskname>\n"
            "Example: /record backup\n\n"
            "The task name can only contain letters, numbers, underscores, and hyphens."
        )
        return
    
    task_name = context.args[0]
    
    # Validate task name
    if not is_valid_task_name(task_name):
        await update.message.reply_text(
            f"Invalid task name '{task_name}'.\n"
            "Use only letters, numbers, underscores, or hyphens (max 64 chars)."
        )
        return
    
    # Check if task already exists
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name FROM tasks WHERE name=?", (task_name,))
    existing = c.fetchone()
    conn.close()
    
    if existing:
        await update.message.reply_text(
            f"Task '{task_name}' already exists.\n"
            "Use a different name or delete it first with /del."
        )
        return
    
    # Initialize recording state in context.user_data
    context.user_data["recording"] = True
    context.user_data["recording_task"] = task_name
    context.user_data["recording_commands"] = []
    
    await update.message.reply_text(
        f"Recording task: {task_name}\n\n"
        "Send me commands one per message.\n"
        "Send /done when finished.\n"
        "Send /cancel to abort.\n\n"
        "Example commands:\n"
        "  echo 'Hello'\n"
        "  ls -la\n"
        "  python script.py"
    )

# ─────────────────────────────────────────────────────────────────────────────
# Telegram: /done
# ─────────────────────────────────────────────────────────────────────────────

async def tg_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    
    if not context.user_data.get("recording", False):
        await update.message.reply_text(
            "No active recording.\n"
            "Use /record <taskname> to start recording."
        )
        return
    
    commands = context.user_data.get("recording_commands", [])
    task_name = context.user_data.get("recording_task", "")
    
    if not commands:
        await update.message.reply_text("No commands recorded. Recording cancelled.")
        context.user_data.clear()
        return
    
    # Save commands to temp file
    temp_file = os.path.join(TASK_DIR, f"{task_name}_temp.txt")
    with open(temp_file, "w") as f:
        for cmd in commands:
            f.write(cmd + "\n")
    
    # Store temp file in context for later trigger
    context.user_data["recording"] = False
    context.user_data["temp_file"] = temp_file
    
    await update.message.reply_text(
        f"Recorded {len(commands)} command(s) for task '{task_name}'.\n\n"
        "Choose a trigger type:\n"
        "/trigger_none - Run immediately\n"
        "/trigger_internet - Run when internet is available\n"
        "/trigger_datetime YYYY-MM-DD HH:MM - Run at a specific time\n\n"
        "Example: /trigger_datetime 2025-12-31 09:00"
    )

# ─────────────────────────────────────────────────────────────────────────────
# Telegram: /cancel
# ─────────────────────────────────────────────────────────────────────────────

async def tg_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    
    if "temp_file" in context.user_data:
        temp_file = context.user_data["temp_file"]
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    context.user_data.clear()
    await update.message.reply_text("Recording cancelled.")

# ─────────────────────────────────────────────────────────────────────────────
# Telegram: /trigger_*
# ─────────────────────────────────────────────────────────────────────────────

async def tg_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    
    if "temp_file" not in context.user_data or "recording_task" not in context.user_data:
        await update.message.reply_text(
            "No pending task. Use /record <taskname> first, then /done, then /trigger_*."
        )
        return
    
    task_name = context.user_data["recording_task"]
    temp_file = context.user_data["temp_file"]
    
    if not os.path.exists(temp_file):
        await update.message.reply_text("No recorded commands found. Please start over with /record.")
        context.user_data.clear()
        return
    
    cmd_name = _get_command_name(update.message.text)
    
    if cmd_name == "/trigger_none":
        trigger_type, trigger_value = "none", ""
    elif cmd_name == "/trigger_internet":
        trigger_type, trigger_value = "internet", "loop"
    elif cmd_name == "/trigger_datetime":
        if not context.args:
            await update.message.reply_text(
                "Usage: /trigger_datetime YYYY-MM-DD HH:MM\n"
                "Example: /trigger_datetime 2025-12-31 09:00"
            )
            return
        trigger_value = " ".join(context.args)
        try:
            datetime.strptime(trigger_value, "%Y-%m-%d %H:%M")
        except ValueError:
            await update.message.reply_text(
                f"Invalid datetime format: '{trigger_value}'\n"
                "Use: YYYY-MM-DD HH:MM  (e.g. 2025-12-31 09:00)"
            )
            return
        trigger_type = "datetime"
    else:
        await update.message.reply_text(
            "Invalid trigger command.\n"
            "Use /trigger_none, /trigger_internet, or /trigger_datetime."
        )
        return
    
    # Save the task permanently
    final_file = os.path.join(TASK_DIR, f"{task_name}.txt")
    if os.path.exists(final_file):
        os.remove(final_file)
    os.rename(temp_file, final_file)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO tasks"
        " (name, file, trigger_type, trigger_value, created_at) VALUES (?,?,?,?,?)",
        (task_name, final_file, trigger_type, trigger_value, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    
    with open(final_file) as f:
        cmd_count = len(f.readlines())
    
    # Clear recording state
    context.user_data.clear()
    
    await update.message.reply_text(
        f"Task '{task_name}' saved successfully!\n"
        f"Trigger:  {trigger_type}\n"
        f"Commands: {cmd_count}\n\n"
        f"Use /inject {task_name} to run this task."
    )

# ─────────────────────────────────────────────────────────────────────────────
# Telegram: /inject
# ─────────────────────────────────────────────────────────────────────────────

async def tg_inject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    
    if not context.args:
        await update.message.reply_text(
            "Usage: /inject <taskname>\n"
            "Example: /inject backup\n\n"
            "Use /list to see available tasks."
        )
        return

    task_name = context.args[0]

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT file, trigger_type, trigger_value FROM tasks WHERE name=?", (task_name,))
    row = c.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text(
            f"Task '{task_name}' not found.\n"
            f"Use /list to see available tasks."
        )
        return

    file_path, trigger_type, trigger_value = row

    if not os.path.exists(file_path):
        await update.message.reply_text(f"Task file missing for '{task_name}'.")
        return

    commands = load_commands(file_path)

    if trigger_type == "none":
        await update.message.reply_text(f"Starting task '{task_name}'...")

        def _run_none():
            lines = run_commands_with_output(commands, task_name=task_name)
            lines.append(f"--- Task '{task_name}' completed ---")
            _send_output_chunks(update, lines, task_name)

        threading.Thread(target=_run_none, daemon=True).start()

    elif trigger_type == "internet":
        await update.message.reply_text(
            f"Internet watchdog started for '{task_name}'.\n"
            "Will execute automatically when internet is available."
        )

        def _run_internet():
            global stop_flag
            while not stop_flag:
                if has_internet():
                    _tg_send(update.message.reply_text(
                        f"Internet detected! Executing task '{task_name}'..."
                    ))
                    lines = run_commands_with_output(
                        commands, internet_mode=True, task_name=task_name
                    )
                    lines.append(f"--- Task '{task_name}' completed ---")
                    _send_output_chunks(update, lines, task_name)
                    break
                time.sleep(5)

        threading.Thread(target=_run_internet, daemon=True).start()

    elif trigger_type == "datetime":
        try:
            target = datetime.strptime(trigger_value, "%Y-%m-%d %H:%M")
        except ValueError:
            await update.message.reply_text(f"Invalid datetime stored: '{trigger_value}'.")
            return

        await update.message.reply_text(
            f"Task '{task_name}' scheduled for {trigger_value}.\n"
            "You will be notified when it completes."
        )

        def _run_datetime():
            global stop_flag
            while datetime.now() < target and not stop_flag:
                time.sleep(5)
            if stop_flag:
                _tg_send(update.message.reply_text(f"Task '{task_name}' was cancelled."))
                return
            _tg_send(update.message.reply_text(
                f"Time reached! Executing task '{task_name}'..."
            ))
            lines = run_commands_with_output(commands, task_name=task_name)
            lines.append(f"--- Task '{task_name}' completed ---")
            _send_output_chunks(update, lines, task_name)

        threading.Thread(target=_run_datetime, daemon=True).start()

# ─────────────────────────────────────────────────────────────────────────────
# Telegram: /cat
# ─────────────────────────────────────────────────────────────────────────────

async def tg_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    
    if not context.args:
        await update.message.reply_text(
            "Usage: /cat <taskname>\n"
            "Example: /cat backup\n\n"
            "Use /list to see available tasks."
        )
        return
    
    task_name = context.args[0]
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT file, trigger_type, trigger_value FROM tasks WHERE name=?", (task_name,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        await update.message.reply_text(f"Task '{task_name}' not found.")
        return
    
    file_path, trigger_type, trigger_value = row
    
    if not os.path.exists(file_path):
        await update.message.reply_text(f"Task file missing for '{task_name}'.")
        return
    
    with open(file_path) as f:
        content = f.read()
    
    response = (
        f"Task: {task_name}\n"
        f"Trigger: {trigger_type}\n"
        f"Value: {trigger_value or '-'}\n"
        + "=" * 30 + "\n"
        + content
    )
    
    if len(response) > 4000:
        response = response[:4000] + "\n... (truncated)"
    
    await update.message.reply_text(response)

# ─────────────────────────────────────────────────────────────────────────────
# Telegram: /del
# ─────────────────────────────────────────────────────────────────────────────

async def tg_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    
    if not context.args:
        await update.message.reply_text(
            "Usage: /del <taskname>\n"
            "Example: /del backup\n\n"
            "Use /list to see available tasks."
        )
        return
    
    task_name = context.args[0]
    
    if delete_task(task_name):
        await update.message.reply_text(f"Task '{task_name}' deleted successfully.")
    else:
        await update.message.reply_text(
            f"Task '{task_name}' not found.\n"
            f"Use /list to see available tasks."
        )

# ─────────────────────────────────────────────────────────────────────────────
# Telegram: /shell
# ─────────────────────────────────────────────────────────────────────────────

async def tg_shell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    
    if not context.args:
        await update.message.reply_text(
            "Usage: /shell <command>\n"
            "Example: /shell ls -la\n"
            "Example: /shell python script.py"
        )
        return
    
    command = " ".join(context.args)
    await update.message.reply_text(f"$ {command}")
    output = execute_shell_command(command)
    
    if not output:
        output = "(no output)"
    
    if len(output) > 4000:
        output = output[:4000] + "\n... (truncated)"
    
    await update.message.reply_text(output)

# ─────────────────────────────────────────────────────────────────────────────
# Telegram: /cd
# ─────────────────────────────────────────────────────────────────────────────

async def tg_cd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    
    if not context.args:
        await update.message.reply_text(f"Current directory: {os.getcwd()}")
        return
    
    path = " ".join(context.args)
    try:
        if path == "~":
            path = os.path.expanduser("~")
        os.chdir(path)
        await update.message.reply_text(f"Changed to: {os.getcwd()}")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

# ─────────────────────────────────────────────────────────────────────────────
# Telegram: /pwd
# ─────────────────────────────────────────────────────────────────────────────

async def tg_pwd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    
    await update.message.reply_text(os.getcwd())

# ─────────────────────────────────────────────────────────────────────────────
# Telegram: /ls
# ─────────────────────────────────────────────────────────────────────────────

async def tg_ls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    
    try:
        items = os.listdir(".")
        if not items:
            await update.message.reply_text("Directory is empty.")
            return
        
        output = "Directory listing:\n\n"
        for item in sorted(items):
            if os.path.isdir(item):
                output += f"[DIR]  {item}/\n"
            else:
                size = os.path.getsize(item)
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f} MB"
                output += f"[FILE] {item} ({size_str})\n"
        
        if len(output) > 4000:
            output = output[:4000] + "\n... (truncated)"
        
        await update.message.reply_text(output)
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

# ─────────────────────────────────────────────────────────────────────────────
# Telegram: /stop
# ─────────────────────────────────────────────────────────────────────────────

async def tg_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global remote_mode_active, authorized_user_id
    
    if not is_authorized(update):
        return
    
    await update.message.reply_text("Stopping remote mode...")
    remote_mode_active = False
    authorized_user_id = None

# ─────────────────────────────────────────────────────────────────────────────
# Telegram: /help
# ─────────────────────────────────────────────────────────────────────────────

async def tg_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"{PROGRAM_NAME.upper()} BOT HELP\n\n"
        "TASK COMMANDS:\n"
        "/list              - List all tasks\n"
        "/record <name>     - Record a new task\n"
        "/inject <name>     - Execute a task\n"
        "/cat <name>        - View task content\n"
        "/del <name>        - Delete a task\n\n"
        "SHELL COMMANDS:\n"
        "/shell <command>   - Run any shell command\n"
        "/cd <directory>    - Change directory\n"
        "/pwd               - Show current directory\n"
        "/ls                - List files in current directory\n\n"
        "OTHER:\n"
        "/stop              - Stop remote mode\n"
        "/help              - Show this help\n\n"
        "EXAMPLES:\n"
        "/record backup\n"
        "/inject backup\n"
        "/cat backup\n"
        "/del backup\n"
        "/shell ls -la\n"
        "/cd /tmp\n"
        "/ls"
    )

# ─────────────────────────────────────────────────────────────────────────────
# Telegram: Message Handler
# ─────────────────────────────────────────────────────────────────────────────

async def tg_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Handle authentication
    if context.user_data.get("awaiting_auth", False):
        await tg_handle_auth(update, context)
        return
    
    # Handle recording session
    if context.user_data.get("recording", False):
        command = update.message.text.strip()
        if command and not command.startswith("/"):
            context.user_data["recording_commands"].append(command)
            await update.message.reply_text(f"Added: {command}")
        else:
            await update.message.reply_text(
                "Send plain text commands (not starting with /) or use /done to finish.\n"
                "Use /cancel to abort."
            )
        return
    
    # Handle unknown input for authorized users
    if is_authorized(update):
        await update.message.reply_text(
            "Unknown command.\n"
            "Send /start to see available commands."
        )
    else:
        await update.message.reply_text(
            "Access denied.\n"
            "Send /start to authenticate."
        )

# ─────────────────────────────────────────────────────────────────────────────
# Bot Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_telegram_bot(bot_token: str):
    global telegram_app, remote_mode_active, bot_event_loop

    async def bot_main():
        global telegram_app, remote_mode_active, bot_event_loop

        bot_event_loop = asyncio.get_event_loop()

        app = ApplicationBuilder().token(bot_token).build()

        # Command handlers
        app.add_handler(CommandHandler("start", tg_start))
        app.add_handler(CommandHandler("list", tg_list))
        app.add_handler(CommandHandler("record", tg_record))
        app.add_handler(CommandHandler("done", tg_done))
        app.add_handler(CommandHandler("cancel", tg_cancel))
        app.add_handler(CommandHandler("trigger_none", tg_trigger))
        app.add_handler(CommandHandler("trigger_internet", tg_trigger))
        app.add_handler(CommandHandler("trigger_datetime", tg_trigger))
        app.add_handler(CommandHandler("inject", tg_inject))
        app.add_handler(CommandHandler("cat", tg_cat))
        app.add_handler(CommandHandler("del", tg_delete))
        app.add_handler(CommandHandler("shell", tg_shell))
        app.add_handler(CommandHandler("cd", tg_cd))
        app.add_handler(CommandHandler("pwd", tg_pwd))
        app.add_handler(CommandHandler("ls", tg_ls))
        app.add_handler(CommandHandler("stop", tg_stop))
        app.add_handler(CommandHandler("help", tg_help))
        
        # Message handler for non-command messages
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tg_message))

        telegram_app = app
        await app.initialize()
        await app.start()
        await app.updater.start_polling()

        while remote_mode_active:
            await asyncio.sleep(0.5)

        await app.updater.stop()
        await app.stop()
        await app.shutdown()

    try:
        asyncio.run(bot_main())
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# CLI Help
# ─────────────────────────────────────────────────────────────────────────────

def show_help():
    sep = f"{C_PRIMARY}" + "=" * 60 + C_RESET
    print(f"\n{sep}")
    print(f"{C_PRIMARY}AVAILABLE COMMANDS{C_RESET}")
    print(sep)
    print(f"\n{C_PRIMARY}MAIN COMMANDS:{C_RESET}")
    print(f"{C_PRIMARY}  record <name>    {C_WHITE}Store a sequence of commands as a task{C_RESET}")
    print(f"{C_PRIMARY}  inject <name>    {C_WHITE}Execute a saved task{C_RESET}")
    print(f"{C_PRIMARY}  list             {C_WHITE}Show all saved tasks{C_RESET}")
    print(f"{C_PRIMARY}  remote           {C_WHITE}Start Telegram remote control{C_RESET}")
    print(f"{C_PRIMARY}  exit             {C_WHITE}Quit {PROGRAM_NAME}{C_RESET}")
    print(f"\n{C_PRIMARY}SUB COMMANDS:{C_RESET}")
    print(f"{C_PRIMARY}  cat <name>       {C_WHITE}View content of a task{C_RESET}")
    print(f"{C_PRIMARY}  del <name>       {C_WHITE}Delete a task{C_RESET}")
    print(f"\n{C_PRIMARY}REMOTE SETUP:{C_RESET}")
    print(f"{C_PRIMARY}  remote_setup     {C_WHITE}Configure Telegram bot credentials{C_RESET}")
    print(f"{C_PRIMARY}  remote_view      {C_WHITE}View current remote configuration{C_RESET}")
    print(f"{C_PRIMARY}  remote_remove    {C_WHITE}Remove remote configuration{C_RESET}")
    print(f"\n{C_PRIMARY}SHELL:{C_RESET}")
    print(f"{C_WHITE}  Any system command works directly at the prompt.")
    print(f"  Examples: ls, pwd, mkdir, rm, cp, mv, python, git, curl, wget{C_RESET}")
    print(f"\n{sep}\n")

# ─────────────────────────────────────────────────────────────────────────────
# Command Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

_TOOL_COMMANDS = {
    "record", "inject", "list", "cat", "del", "delete",
    "remote", "remote_setup", "remote_view", "remote_remove",
    "help", "exit", "quit", "clear",
}

def is_tool_command(cmd: str) -> bool:
    lower = cmd.lower().strip()
    if lower in _TOOL_COMMANDS:
        return True
    for tc in _TOOL_COMMANDS:
        if lower.startswith(tc + " "):
            return True
    return False

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    global stop_flag, current_user

    logging.basicConfig(level=logging.CRITICAL)
    for name in ("telegram", "httpx", "httpcore", "asyncio", "urllib3"):
        logging.getLogger(name).setLevel(logging.CRITICAL)

    init_db()

    username = login()
    if not username:
        print_primary("Login failed. Exiting.")
        sys.exit(1)

    current_user = username
    path_manager = PathManager()
    display_interface(username)

    while True:
        try:
            command = display_prompt(username, path_manager.current_path)

            if not command or command.isspace():
                continue

            # cd handled separately to keep path_manager in sync
            if command.startswith("cd ") or command.strip() == "cd":
                arg = command[3:].strip() if len(command) > 3 else "~"
                success, result = path_manager.change(arg)
                if not success:
                    print_error(result)
                continue

            if is_tool_command(command):
                parts = command.split(maxsplit=1)
                cmd   = parts[0].lower()
                arg   = parts[1].strip() if len(parts) > 1 else ""

                if cmd in ("exit", "quit"):
                    stop_flag = True
                    print(f"\n{C_PRIMARY}Goodbye!{C_RESET}")
                    sys.exit(0)

                elif cmd == "clear":
                    display_interface(username)

                elif cmd == "help":
                    show_help()

                elif cmd == "list":
                    list_tasks()

                elif cmd == "record":
                    if not arg:
                        print_error("Usage: record <taskname>")
                    else:
                        record_task(arg)

                elif cmd == "inject":
                    if not arg:
                        print_error("Usage: inject <taskname>")
                    else:
                        inject_task(arg)

                elif cmd == "cat":
                    if not arg:
                        print_error("Usage: cat <taskname>")
                    else:
                        cat_task(arg)

                elif cmd in ("del", "delete"):
                    if not arg:
                        print_error("Usage: del <taskname>")
                    else:
                        if not delete_task(arg):
                            print_error(f"Task '{arg}' not found.")

                elif cmd == "remote":
                    remote_command()

                elif cmd == "remote_setup":
                    setup_remote_mode()

                elif cmd == "remote_view":
                    view_remote_config()

                elif cmd == "remote_remove":
                    if remove_remote_config():
                        print_primary("Remote configuration removed successfully.")
                    else:
                        print_error("No remote configuration found.")

                else:
                    print_error(f"Unknown command: {command}")
                    print(f"{C_PRIMARY}Type 'help' for available commands.{C_RESET}")

            else:
                output = execute_direct_command(command)
                if output == "CLEAR":
                    display_interface(username)
                elif output:
                    print(f"{C_WHITE}{output}{C_RESET}")
                path_manager.sync()

        except KeyboardInterrupt:
            print(f"\n{C_PRIMARY}Use 'exit' to quit.{C_RESET}")
            continue
        except EOFError:
            print(f"\n{C_PRIMARY}Goodbye!{C_RESET}")
            break
        except Exception as e:
            print_error(str(e))


if __name__ == "__main__":
    main()