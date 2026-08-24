import fcntl
import json
import os
import re
import sys
import time
from pathlib import Path

import psutil


STATE_PATH = Path("/tmp/codex-monitor-state.json")
TRAILING_MARKDOWN = re.compile(r"[\s*_`'\"\])}]+$")


def find_codex_cli_process():
    try:
        process = psutil.Process(os.getppid())

        for candidate in (process, *process.parents()):
            if candidate.name().lower() == "codex" and candidate.terminal():
                return {
                    "pid": candidate.pid,
                    "terminal": os.path.basename(candidate.terminal()),
                }
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass

    return None


def message_asks_question(message):
    text = TRAILING_MARKDOWN.sub("", message or "")
    return text.endswith("?")


def status_for_event(event):
    event_name = event.get("hook_event_name")

    if event_name == "Stop":
        if message_asks_question(event.get("last_assistant_message")):
            return "waiting_answer"
        return "completed"

    if event_name == "PermissionRequest":
        return "waiting_approval"

    if event_name == "PreToolUse" and event.get("tool_name") == "request_user_input":
        return "waiting_answer"

    return "working"


def update_state(event, cli_process):
    session_id = event.get("session_id") or str(cli_process["pid"])
    cwd = event.get("cwd") or ""

    with STATE_PATH.open("a+", encoding="utf-8") as state_file:
        fcntl.flock(state_file, fcntl.LOCK_EX)
        state_file.seek(0)

        try:
            state = json.load(state_file)
        except json.JSONDecodeError:
            state = {"sessions": {}}

        sessions = state.setdefault("sessions", {})

        if event.get("hook_event_name") == "SessionEnd":
            sessions.pop(session_id, None)
        else:
            project = os.path.basename(cwd.rstrip(os.sep)) or cwd or "sem-projeto"
            sessions[session_id] = {
                **cli_process,
                "cwd": cwd,
                "project": project,
                "status": status_for_event(event),
                "updated_at": time.time(),
            }

        state_file.seek(0)
        state_file.truncate()
        json.dump(state, state_file, ensure_ascii=False)
        state_file.flush()
        fcntl.flock(state_file, fcntl.LOCK_UN)


def main():
    try:
        event = json.load(sys.stdin)
        cli_process = find_codex_cli_process()

        if cli_process:
            update_state(event, cli_process)
    except (OSError, ValueError, psutil.Error):
        pass

    print("{}")


if __name__ == "__main__":
    main()
