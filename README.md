![image alt](https://github.com/Joyalmaxwel04/Mudrep/blob/81c87da5cc7d04d1387c535388486f4b23bec9e9/Thumbnail/icons.png)
Python | CLI | Automation | Telegram Remote
# mudrep — CLI Tool

> **mudrep** is a terminal-based task automation and remote control tool that lets you record, schedule, and inject shell command sequences from a styled CLI interface — and control everything remotely through a Telegram bot.

---

## What Is It?

mudrep is a local command-line application built in Python. It runs in your terminal, and gives you a personal task manager where you can store groups of shell commands as named "tasks" and run them on demand, on a schedule, or when internet becomes available. It also ships a full Telegram bot integration so you can trigger and monitor everything from your phone or any device from anywhere else in the world only by access through internet.


![image alt](https://github.com/Joyalmaxwel04/Mudrep/blob/595a2c03c803ab03fc68257cf77d09639fe77c17/Thumbnail/file_000000004cb0720b8a435c4544758d47.png)
![image_alt](https://github.com/Joyalmaxwel04/Mudrep/blob/0c93c74fc2cfaa67ee87da2197405f4cc3a46afb/Thumbnail/file_00000000ffa8720ba8eba7a7f907b4bf.png)

## Features

### CLI Interface
- Two-line prompt showing your username and current path
- Coral orange color scheme (`#FF7F50`) throughout the interface
- Full shell passthrough — any system command works directly at the prompt
- Login and account system with password hashing (SHA-256)
- First-run registration flow for new users
- `clear` command redraws the full interface

### Task Management
- **record** — interactively record a sequence of shell commands as a named task
- **inject** — execute a saved task by name
- **list** — display all saved tasks in a formatted table
- **cat** — view the contents and metadata of a task
- **del** — delete a task and its file

### Task Triggers
- **none** — runs immediately when injected
- **internet** — runs automatically as soon as internet connectivity is detected (watchdog thread)
- **datetime** — runs at a scheduled date and time (format: `YYYY-MM-DD HH:MM`)

### Telegram Remote Control
- Full Telegram bot integration with password authentication
- Bot runs silently in the background — no logs shown in the terminal
- Control tasks and shell from your phone while the program runs on your machine
- `/stop` from Telegram cleanly exits remote mode without hanging the CLI
- Supports all task operations and shell commands remotely

### Telegram Bot Commands
| Command | Description |
|---|---|
| `/start` | Authenticate and see the command list |
| `/list` | List all saved tasks |
| `/record <name>` | Start recording a new task |
| `/done` | Finish recording commands |
| `/cancel` | Cancel current recording |
| `/trigger_none` | Save task with immediate trigger |
| `/trigger_internet` | Save task with internet watchdog trigger |
| `/trigger_datetime YYYY-MM-DD HH:MM` | Save task with scheduled trigger |
| `/inject <name>` | Execute a task and receive the output |
| `/cat <name>` | View task content |
| `/del <name>` | Delete a task |
| `/shell <cmd>` | Run any shell command |
| `/cd <dir>` | Change directory |
| `/pwd` | Show current directory |
| `/ls` | List files in current directory |
| `/stop` | Stop remote mode |
| `/help` | Show all commands |

![image_alt](https://github.com/Joyalmaxwel04/Mudrep/blob/f67a9619b0bdc8bffd93ef73494179ae8dde8a61/Thumbnail/file_000000005974720ba593d0ed7f5d406b.png)

## Requirements

- Python 3.9 or higher
- A Telegram account and bot token from [@BotFather](https://t.me/BotFather)

### Install dependencies

```bash
pip install python-telegram-bot
```

---

## Installation

```bash
# Clone the repository
git clone https://github.com/Joyalmaxwel04/Mudrep.git
cd mudrep

# Install dependencies
pip install python-telegram-bot

# Run the tool
python3 mudkip.py
```

---

## First Run — Account Setup

On the very first launch, mudrep will detect no existing users and guide you through creating your account:

```
=== Welcome to mudrep - First Time Setup ===
No accounts found. Please create your account.

Create username: meaghan
Create password:
Confirm password:

Account created successfully. Welcome, meaghan
```

Every subsequent launch will show the login screen:

```
=== mudrep Login ===
Username: meaghan
Password:

Login successful. Welcome, meaghan
```

You have 3 attempts before access is denied.

---

## Usage

### Recording a Task

```
record <name>
```

You will enter record mode and type commands one by one:

```
[RECORD MODE] Type commands one by one. Type 'exit' to finish.
record> mkdir -p ~/backups
record> cp -r ~/Documents ~/backups/docs
record> tar -czf ~/backups/docs.tar.gz ~/backups/docs
record> exit

Trigger Types:
  1. none     (run immediately)
  2. internet (run when internet available)
  3. datetime (run at a specific date/time)
Choose trigger (1/2/3): 1

[OK] Task 'backup' saved with 3 command(s).
```

### Running a Task

```
inject <recordname>
```

### Viewing All Tasks

```
list
```

### Viewing a Task's Contents

```
cat <recordname>
```

### Deleting a Task

```
del <recordname>
```

---

## Setting Up Telegram Remote Control

### Step 1 — Create a Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the instructions
3. Copy the bot token BotFather provides (format: `1234567890:ABCdef...`)

### Step 2 — Configure mudrep

At the mudrep prompt, type:

```
remote_setup
```

Enter your bot token and set a remote access password when prompted. This password protects your bot from unauthorized access.

### Step 3 — Start Remote Mode

```
remote
```

mudrep authenticates you, starts the bot silently in the background, and returns a prompt. Open Telegram, find your bot, and send `/start`. The bot will ask for your remote access password. Once authenticated, all commands are available.

To stop remote mode, type `exit` at the CLI prompt or send `/stop` from Telegram.

---

## Task Name Rules

Task names must:
- Contain only letters, numbers, underscores (`_`), or hyphens (`-`)
- Be between 1 and 64 characters long
- Not contain spaces, slashes, dots, or special characters

Valid examples: `backup`, `my-task`, `deploy_v2`

---

## Files Created by mudrep

| File | Purpose |
|---|---|
| `mudrep_users.json` | Stores user accounts (hashed passwords) |
| `remote_config.json` | Stores bot token and remote password hash |
| `tasks.db` | SQLite database of all recorded tasks |
| `tasks/` | Folder containing task command files (`.txt`) |

---

## Project Structure

```
mudrep/
├── mudrep.py          # Main application file
├── mudrep_users.json  # Auto-generated on first run
├── remote_config.json # Auto-generated after remote_setup
├── tasks.db           # Auto-generated SQLite database
├── tasks/             # Auto-generated task files directory
└── README.md
```

---

## Security Notes

- All passwords are hashed with SHA-256 before storage — plain text passwords are never saved
- The Telegram bot requires password authentication before any command is accepted
- Only one Telegram user can be authorized at a time per session
- Remote mode must be explicitly started; the bot does not run automatically on launch

---

## Educational Purpose

mudrep was built as a learning project covering:

- **Python CLI design** — building structured terminal interfaces with ANSI colors
- **SQLite integration** — storing and querying structured data with Python's built-in `sqlite3`
- **Threading** — running background tasks (internet watchdog, datetime scheduler, Telegram bot) alongside an interactive CLI using `threading.Thread` and `asyncio.run_coroutine_threadsafe`
- **Async Python** — understanding `asyncio` event loops, how to share them safely across threads, and structuring a bot with `python-telegram-bot`
- **Process management** — spawning and capturing output from subprocesses with `subprocess.run`
- **Authentication design** — implementing a simple but correct login system with hashing, file persistence, and brute-force limiting
- **Bot development** — building a full-featured Telegram bot with command handlers, conversation state (`context.user_data`), and multi-step flows

---

## Productivity Use Cases

- Automate repetitive multi-step terminal workflows into single commands
- Schedule maintenance scripts to run at a specific time without needing `cron`
- Run tasks as soon as a machine reconnects to the internet (internet trigger)
- Monitor and control your machine remotely from your phone via Telegram
- Quick task library for commands you use regularly but don't want to retype

---

## Disclaimer

> This tool is for **educational purposes only**.
> Do not use it to access systems you do not own or have explicit permission to use.
> Misuse may result in legal consequences.
> The author is not responsible for any damage or illegal activity caused by use of this software.

---

## License

This project is open source. Use it freely for personal and educational purposes.

---

*Built with Python 3 · python-telegram-bot · SQLite*
