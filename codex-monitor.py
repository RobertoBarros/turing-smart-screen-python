import fcntl
import json
import os
import time
from pathlib import Path

import psutil

from library.lcd.lcd_comm_rev_a_usbmac import LcdCommRevAUsbMac


REFRESH_INTERVAL_SECONDS = 2
PAGE_INTERVAL_SECONDS = 4
ROWS_PER_PAGE = 4
STATE_PATH = Path("/tmp/codex-monitor-state.json")

STATUS_LABELS = {
    "working": "TRABALHANDO",
    "completed": "RESPOSTA PRONTA",
    "waiting_answer": "AGUARDA RESPOSTA",
    "waiting_approval": "AGUARDA APROVAÇÃO",
}

STATUS_PRIORITY = {
    "waiting_approval": 0,
    "waiting_answer": 1,
    "completed": 2,
    "working": 3,
}


def active_codex_cli_instances():
    instances = []

    for process in psutil.process_iter(["pid", "name", "terminal", "cwd"]):
        try:
            name = (process.info["name"] or "").lower()
            terminal = process.info["terminal"]

            if name != "codex" or not terminal:
                continue

            cwd = process.info["cwd"] or ""
            instances.append(
                {
                    "pid": process.info["pid"],
                    "terminal": os.path.basename(terminal),
                    "project": os.path.basename(cwd.rstrip(os.sep)) or cwd or "sem-projeto",
                }
            )
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue

    return instances


def read_session_states():
    if not STATE_PATH.exists():
        return {}

    try:
        with STATE_PATH.open("r", encoding="utf-8") as state_file:
            fcntl.flock(state_file, fcntl.LOCK_SH)
            state = json.load(state_file)
            fcntl.flock(state_file, fcntl.LOCK_UN)
    except (OSError, json.JSONDecodeError):
        return {}

    return state.get("sessions", {})


def display_entries(instances, session_states):
    states_by_pid = {
        session["pid"]: session
        for session in session_states.values()
        if session.get("pid")
    }
    entries = []

    for instance in instances:
        state = states_by_pid.get(instance["pid"], {})
        entries.append(
            {
                **instance,
                "project": state.get("project", instance["project"]),
                "status": state.get("status", "working"),
            }
        )

    return sorted(
        entries,
        key=lambda entry: (
            STATUS_PRIORITY.get(entry["status"], 99),
            entry["terminal"],
        ),
    )


def truncate(value, maximum_length=15):
    if len(value) <= maximum_length:
        return value

    return f"{value[:maximum_length - 1]}…"


def display_text(entries, page):
    if not entries:
        return "CODEX CLI\n\nNENHUMA INSTÂNCIA"

    page_count = (len(entries) + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE
    start = page * ROWS_PER_PAGE
    lines = ["CODEX CLI"]

    if page_count > 1:
        lines.append(f"PÁGINA {page + 1}/{page_count}")

    for entry in entries[start:start + ROWS_PER_PAGE]:
        identifier = f"{entry['terminal']} · {truncate(entry['project'])}"
        lines.extend(("", identifier, STATUS_LABELS[entry["status"]]))

    return "\n".join(lines)


def main():
    lcd = LcdCommRevAUsbMac()
    lcd.InitializeComm()
    lcd.Clear()
    previous_text = None

    try:
        while True:
            entries = display_entries(
                active_codex_cli_instances(),
                read_session_states(),
            )
            page_count = max(1, (len(entries) + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)
            page = int(time.monotonic() / PAGE_INTERVAL_SECONDS) % page_count
            text = display_text(entries, page)

            if text != previous_text:
                lcd.DisplayText(
                    text,
                    width=lcd.get_width(),
                    height=lcd.get_height(),
                    font_size=20,
                    font_color=(255, 255, 255),
                    background_color=(0, 0, 0),
                    align="center",
                    anchor="mm",
                )
                previous_text = text

            time.sleep(REFRESH_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        pass
    finally:
        lcd.closeSerial()


if __name__ == "__main__":
    main()
