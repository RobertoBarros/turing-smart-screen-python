import fcntl
import json
import os
import time
from pathlib import Path

import psutil
from PIL import Image, ImageDraw, ImageFont

from library.lcd.lcd_comm_rev_a_usbmac import LcdCommRevAUsbMac


REFRESH_INTERVAL_SECONDS = 2
PAGE_INTERVAL_SECONDS = 4
ROWS_PER_PAGE = 4
STATE_PATH = Path("/tmp/codex-monitor-state.json")
FONT_PATH = "res/fonts/roboto/Roboto-Medium.ttf"
BOLD_FONT_PATH = "res/fonts/roboto/Roboto-Bold.ttf"
BACKGROUND_COLOR = (11, 15, 20)

STATUS_LABELS = {
    "working": "TRABALHANDO",
    "completed": "RESPOSTA PRONTA",
    "waiting_answer": "AGUARDA RESPOSTA",
    "waiting_approval": "AGUARDA APROVAÇÃO",
}

STATUS_COLORS = {
    "working": ((9, 45, 72), (74, 222, 255)),
    "completed": ((9, 58, 38), (74, 222, 128)),
    "waiting_answer": ((69, 43, 0), (255, 196, 61)),
    "waiting_approval": ((71, 20, 27), (255, 99, 112)),
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

    return sorted(entries, key=lambda entry: entry["project"].casefold())


def truncate(value, maximum_length=28):
    if len(value) <= maximum_length:
        return value

    return f"{value[:maximum_length - 1]}…"


def render_dashboard(width, height, entries, page):
    image = Image.new("RGB", (width, height), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(BOLD_FONT_PATH, 18)
    project_font = ImageFont.truetype(FONT_PATH, 18)
    status_font = ImageFont.truetype(BOLD_FONT_PATH, 17)

    draw.text((14, 14), "CODEX CLI", font=title_font, fill=(255, 255, 255))

    if not entries:
        draw.text(
            (14, 64),
            "NENHUMA INSTÂNCIA",
            font=project_font,
            fill=(139, 152, 165),
        )
        return image

    page_count = (len(entries) + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE
    start = page * ROWS_PER_PAGE

    if page_count > 1:
        page_text = f"{page + 1}/{page_count}"
        page_box = draw.textbbox((0, 0), page_text, font=status_font)
        draw.text(
            (width - 14 - (page_box[2] - page_box[0]), 17),
            page_text,
            font=status_font,
            fill=(139, 152, 165),
        )

    card_gap = 8
    card_x = 10
    card_y = 50
    card_width = width - 20
    card_height = (height - card_y - 10 - card_gap * (ROWS_PER_PAGE - 1)) // ROWS_PER_PAGE

    for index, entry in enumerate(entries[start:start + ROWS_PER_PAGE]):
        y = card_y + index * (card_height + card_gap)
        background_color, text_color = STATUS_COLORS[entry["status"]]
        draw.rounded_rectangle(
            (card_x, y, card_x + card_width, y + card_height),
            radius=12,
            fill=background_color,
        )
        draw.text(
            (card_x + 14, y + 16),
            truncate(entry["project"]),
            font=project_font,
            fill=(255, 255, 255),
        )
        draw.text(
            (card_x + 14, y + 50),
            STATUS_LABELS[entry["status"]],
            font=status_font,
            fill=text_color,
        )

    return image


def main():
    lcd = LcdCommRevAUsbMac()
    lcd.InitializeComm()
    lcd.Clear()
    previous_state = None

    try:
        while True:
            entries = display_entries(
                active_codex_cli_instances(),
                read_session_states(),
            )
            page_count = max(1, (len(entries) + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)
            page = int(time.monotonic() / PAGE_INTERVAL_SECONDS) % page_count
            display_state = (entries, page)

            if display_state != previous_state:
                lcd.DisplayPILImage(
                    render_dashboard(
                        lcd.get_width(),
                        lcd.get_height(),
                        entries,
                        page,
                    )
                )
                previous_state = display_state

            time.sleep(REFRESH_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        pass
    finally:
        lcd.closeSerial()


if __name__ == "__main__":
    main()
