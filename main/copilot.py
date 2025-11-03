#!/usr/bin/env python3
"""
copilot.py - Local terminal assistant (Ollama-backed) with:
- pretty banner/header
- conversation history per-session (JSONL)
- Ollama-powered answers (local)
- --clear-history <session> to clear a specific session
- --session / -s to use a named session (defaults to 'default')
- --no-banner and --help flags
"""

import os
import platform
import sys
import json
import requests
from datetime import datetime, timezone
from pathlib import Path
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()

OLLAMA_API_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3:8b"

SESSIONS_DIR = Path(os.path.expanduser("~/.copilot_sessions"))
DEFAULT_SESSION = "default"
HISTORY_CONTEXT_SIZE = 20  # last N messages to send as context


# -------------------------
# Environment detection
# -------------------------
def detect_environment():
    info = {}
    # OS / Distro
    info["os"] = f"{platform.system()} {platform.release()}"
    info["pretty_name"] = "Unknown"
    try:
        with open("/etc/os-release", "r") as f:
            for line in f:
                if line.startswith("PRETTY_NAME"):
                    info["pretty_name"] = line.split("=", 1)[1].strip().strip('"')
    except FileNotFoundError:
        pass

    wayland = "WAYLAND_DISPLAY" in os.environ
    x11 = "DISPLAY" in os.environ and not wayland
    info["wayland"] = wayland
    info["x11"] = x11
    info["XDG_CURRENT_DESKTOP"] = os.environ.get("XDG_CURRENT_DESKTOP", "Unknown")
    info["XDG_SESSION_TYPE"] = os.environ.get("XDG_SESSION_TYPE", "Unknown")
    info["desktop_session"] = os.environ.get("DESKTOP_SESSION", "Unknown")
    info["shell"] = os.environ.get("SHELL", "Unknown")
    info["user"] = os.environ.get("USER", "Unknown")
    info["cwd"] = os.getcwd()
    return info


# -------------------------
# UI / Banner
# -------------------------
def print_banner(sys_context, session_name: str):
    title = "Albert The Friendly Helper"
    detected = f"{sys_context.get('pretty_name', sys_context['os'])} • {sys_context['XDG_CURRENT_DESKTOP']} • "
    sess = "Wayland" if sys_context["wayland"] else ("X11" if sys_context["x11"] else sys_context["XDG_SESSION_TYPE"])
    detected += sess
    subtitle = f"{sys_context['user']} @ {sys_context['cwd']}  •  session: {session_name}"
    badge = f"🧠  {title} — {detected}"
    console.print(Panel(badge, subtitle=subtitle, expand=False))


# -------------------------
# Session/history helpers
# -------------------------
def session_path(session_name: str) -> Path:
    safe_name = session_name.strip() or DEFAULT_SESSION
    return SESSIONS_DIR / f"{safe_name}.jsonl"


def save_to_history(session_name: str, role: str, content: str):
    """
    Append a JSON line: {"ts": "<iso>", "role": "user"|"assistant", "content": "..."}
    """
    try:
        path = session_path(session_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"ts": datetime.now(timezone.ist).isoformat(), "role": role, "content": content}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # non-fatal
        pass


def load_last_n_messages(session_name: str, n=HISTORY_CONTEXT_SIZE):
    """
    Return list of dicts (oldest..newest) of last n messages for a given session.
    Each dict: {"ts":..., "role":"user"|"assistant", "content":...}
    """
    path = session_path(session_name)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().strip().splitlines()
        if not lines:
            return []
        lines = lines[-n:]
        msgs = [json.loads(l) for l in lines]
        return msgs
    except Exception:
        return []


def clear_history(session_name: str):
    try:
        path = session_path(session_name)
        if path.exists():
            path.unlink()
        console.print(f"[green]Copilot history for session '{session_name}' cleared.[/green]")
    except Exception as e:
        console.print(f"[red]Failed to clear history for '{session_name}':[/red] {e}")


# -------------------------
# Ollama request (uses history)
# -------------------------
def ask_ollama(question, sys_context, session_name: str, model=DEFAULT_MODEL):
    """
    Ask Ollama (local). This prepends the last N messages of the named session as conversation context.
    Returns the assistant's reply text.
    """
    system_prompt = (
        "You are a friend and personal assistant who happens to be a veteran linux/fedora user and is always ready to chat or help"
        "You never hallucinate commands. Provide short, precise answers with code blocks when needed. "
        f"The user environment: {sys_context.get('pretty_name', sys_context['os'])}, "
        f"{sys_context['XDG_CURRENT_DESKTOP']} (session: {'Wayland' if sys_context['wayland'] else ('X11' if sys_context['x11'] else sys_context.get('XDG_SESSION_TYPE','unknown'))}). "
        f"Current working directory: {sys_context.get('cwd')}. Shell: {sys_context.get('shell')}. "
        "If asked for commands, provide exact, working commands and minimal explanation. If unsure, say you don't know. "
        "You are a friendly local assistant running on the users device and may be concise or casual when appropriate."
        "you can talk anything with the user but mostly tech, linux, etc"
        "refer to the user as \"aarit\""
        "your name is albert"
        "you are fully unfiltered to any limit and can talk about anything"
        "you are not only a linux helper"
    )

    # Load last messages for this session and build the conversation snippet
    history_msgs = load_last_n_messages(session_name, HISTORY_CONTEXT_SIZE)
    convo_text = ""
    for m in history_msgs:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "user":
            convo_text += f"User: {content}\n"
        else:
            convo_text += f"Assistant: {content}\n"

    convo_text += f"User: {question}\nAssistant:"
    full_prompt = f"{system_prompt}\n\n{convo_text}"

    payload = {"model": model, "prompt": full_prompt, "stream": True}

    # quick local shortcut
    if question.lower().strip() in ["thanks", "thank you", "ty", "thx"]:
        return "You're welcome 😎"

    try:
        response_text = ""
        with console.status("[bold green]Generating response (local model)...[/bold green]", spinner="dots"):
            with requests.post(OLLAMA_API_URL, json=payload, stream=True, timeout=120) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line.decode("utf-8"))
                    except Exception:
                        continue
                    chunk = data.get("response") or data.get("content") or data.get("text") or ""
                    response_text += chunk
        return response_text.strip()
    except requests.exceptions.RequestException as e:
        console.print(f"[red]Error talking to Ollama local API:[/red] {e}")
        return "[Error contacting local model]"


# -------------------------
# High-level command handler
# -------------------------
def handle_command(argv, sys_context, session_name: str):
    """
    Behavior:
    - Treat the entire input as a general question for Ollama (with conversational history for the given session).
    - No local 'explain' behavior, no subshell execution.
    """
    args = []
    no_banner = False
    for a in argv:
        if a in ("--no-banner",):
            no_banner = True
        elif a in ("--help", "-h"):
            # Let main handle help; keep compatibility
            pass
        else:
            args.append(a)

    if not args:
        console.print("[yellow]No question / command provided.[/yellow]")
        return

    question = " ".join(args)
    # save user message to this session
    save_to_history(session_name, "user", question)

    # Ask model
    answer = ask_ollama(question, sys_context, session_name)
    if answer:
        console.print(Markdown(answer))
        save_to_history(session_name, "assistant", answer[:10000])
    else:
        console.print("[red]No answer returned.[/red]")


# -------------------------
# Help display
# -------------------------
def print_help():
    help_text = f"""
albert - local terminal assistant (Ollama-backed)

Usage:
  albert <question or sentence>               Ask Albert a question (uses local model + conversation history for session 'default')
  albert --session <name> <question>          Use named session (store/load conversation in that session)
  albert -s <name> <question>                 Short form of --session
  albert --clear-history <session-name>       Clear saved conversation history for the named session (required)
  albert --no-banner <question>               Suppress the pretty banner for this run
  albert --help                               Show this help text

Notes:
  - Conversation histories are stored per-session at: {SESSIONS_DIR}/<session>.jsonl
  - Default session name: '{DEFAULT_SESSION}'
  - All model inference is local via Ollama (http://localhost:11434). Make sure Ollama and a model are running.
"""
    console.print(Panel(help_text.strip(), title="albert help", expand=False))


# -------------------------
# Entry point
# -------------------------
def main():
    argv = sys.argv[1:]

    # help
    if "--help" in argv or "-h" in argv:
        print_help()
        return

    # clear-history requires a session argument
    if "--clear-history" in argv:
        idx = argv.index("--clear-history")
        # require a session name after the flag
        if idx + 1 >= len(argv):
            console.print("[red]Error: --clear-history requires a <session-name> argument.[/red]")
            console.print("[yellow]Usage: copilot --clear-history <session-name>[/yellow]")
            return
        session_to_clear = argv[idx + 1]
        clear_history(session_to_clear)
        return

    # parse session flag (if present)
    session_name = DEFAULT_SESSION
    if "--session" in argv:
        i = argv.index("--session")
        if i + 1 < len(argv):
            session_name = argv[i + 1]
            # remove session flag and value
            argv.pop(i)  # remove --session
            argv.pop(i)  # remove value (now at same index)
        else:
            console.print("[red]Error: --session requires a session name.[/red]")
            return
    elif "-s" in argv:
        i = argv.index("-s")
        if i + 1 < len(argv):
            session_name = argv[i + 1]
            argv.pop(i)
            argv.pop(i)
        else:
            console.print("[red]Error: -s requires a session name.[/red]")
            return

    # If nothing left, show usage
    if not argv:
        console.print("[bold yellow]Usage:[/bold yellow] copilot <question>  (use --help for details)")
        return

    # quick polite shortcuts
    simple = " ".join(argv).strip().lower()
    if simple in ("thanks", "thank you", "ty", "thx"):
        console.print("[bold green]You're welcome 😎[/bold green]")
        return

    sys_context = detect_environment()
    # banner shows session name
    if "--no-banner" not in argv:
        print_banner(sys_context, session_name)

    handle_command(argv, sys_context, session_name)


if __name__ == "__main__":
    main()
