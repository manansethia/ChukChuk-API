import html as _html
import re
from datetime import datetime
from typing import Any


def today_str() -> str:
    return datetime.now().strftime("%d-%b-%Y")


def _strip_html(html_text: str) -> str:
    html_text = re.sub(r"(?is)<script.*?>.*?</script>", "", html_text)
    html_text = re.sub(r"(?is)<style.*?>.*?</style>", "", html_text)
    return re.sub(r"<[^>]+>", "", html_text)


def extract_status_lines(html_text: str) -> list[str]:
    text = _strip_html(html_text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    keywords = [
        "Arrived", "Arrive", "Arriving", "Departed", "Depart", "Departure",
        "On Time", "Yet to start", "Reached Destination", "Current Position",
        "Last Updates On", "Start Date",
    ]
    matches: list[str] = []
    for ln in lines:
        lnl = ln.lower()
        for kw in keywords:
            if kw.lower() in lnl:
                matches.append(ln)
                break
    seen: set[str] = set()
    uniq: list[str] = []
    for m in matches:
        if m not in seen:
            uniq.append(m)
            seen.add(m)
    return uniq


def _clean_line(line: str) -> str:
    line = _html.unescape(line)
    line = line.replace("\xa0", " ")
    line = re.sub(r"\s+", " ", line)
    line = re.sub(r"Last Updates On(?=\d)", "Last Updates On ", line)
    return line.strip(" \t\n\r\u00a0")


def _parse_last_update_dt(lines: list[str]) -> datetime | None:
    last_updates: list[datetime] = []
    for ln in lines:
        m = re.search(
            r"Last Updates On\s*(?P<date>\d{1,2}-[A-Za-z]{3}-\d{4})(?:\s+(?P<time>\d{1,2}:\d{2}))?",
            ln, flags=re.I,
        )
        if not m:
            continue
        date = m.group("date")
        time = m.group("time") or "00:00"
        try:
            last_updates.append(datetime.strptime(f"{date} {time}", "%d-%b-%Y %H:%M"))
        except Exception:
            continue
    return max(last_updates) if last_updates else None


def _build_event_dt(*, date_part: str | None, time_part: str | None, last_update_dt: datetime | None) -> datetime | None:
    time_part = time_part or "00:00"
    if date_part:
        if re.match(r"\d{1,2}-[A-Za-z]{3}-\d{4}$", date_part):
            ds = date_part
        else:
            yr = last_update_dt.year if last_update_dt else datetime.now().year
            ds = f"{date_part}-{yr}"
        try:
            return datetime.strptime(f"{ds} {time_part}", "%d-%b-%Y %H:%M")
        except Exception:
            return None
    if last_update_dt:
        try:
            return datetime.strptime(
                f"{last_update_dt.strftime('%d-%b-%Y')} {time_part}", "%d-%b-%Y %H:%M"
            )
        except Exception:
            return None
    return None


def _detect_status(lines: list[str]) -> str:
    """Detect the status of a journey block from its lines."""
    text = " ".join(lines).lower()
    if "yet to start" in text:
        return "scheduled"
    if "reached destination" in text:
        return "completed"
    if "current position" in text or "departed" in text or "arrived" in text:
        return "running"
    return "unknown"


def _parse_events(lines: list[str], last_update_dt: datetime | None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for ln in lines:
        if not re.search(r"\b(arrived|arrive|arriving|departed|depart|departure)\b", ln, flags=re.I):
            continue

        ev: dict[str, Any] = {
            "raw": ln, "type": None, "station": None,
            "code": None, "datetime": None, "delay": None,
        }

        dm = re.search(r"Delay[:\-\s]*\(?\s*(?:Delay\s*)?([0-9:]{1,5})\)?", ln, flags=re.I)
        if dm:
            ev["delay"] = dm.group(1)

        m = re.search(
            r"\b(Departed|Arrived)\b\s+(?:from|at)\s+(?P<station>[^()]+?)\s*\(\s*(?P<code>[A-Z0-9]{1,6})\s*\)",
            ln, flags=re.I,
        )
        if m:
            ev["type"] = m.group(1).title()
            ev["station"] = m.group("station").strip()
            ev["code"] = m.group("code").strip()
            mtime = re.search(r"(\d{1,2}:\d{2})", ln)
            mdate = re.search(r"(\d{1,2}-[A-Za-z]{3}(?:-\d{4})?)", ln)
            ev["datetime"] = _build_event_dt(
                date_part=mdate.group(1) if mdate else None,
                time_part=mtime.group(1) if mtime else None,
                last_update_dt=last_update_dt,
            )
            if ev["type"] and ev["station"]:
                events.append(ev)
            continue

        mverb = re.search(r"\b(Departed|Arrived)\b", ln, flags=re.I)
        if mverb:
            ev["type"] = mverb.group(1).title()
            mtime = re.search(r"(\d{1,2}:\d{2})", ln)
            mdate = re.search(r"(\d{1,2}-[A-Za-z]{3}(?:-\d{4})?)", ln)
            ev["datetime"] = _build_event_dt(
                date_part=mdate.group(1) if mdate else None,
                time_part=mtime.group(1) if mtime else None,
                last_update_dt=last_update_dt,
            )
            if ev["datetime"] and ev["type"]:
                events.append(ev)

    # Deduplicate
    seen: set[tuple[Any, Any, Any]] = set()
    uniq: list[dict[str, Any]] = []
    for e in events:
        key = (e.get("type"), e.get("station"), e.get("datetime"))
        if key not in seen:
            seen.add(key)
            uniq.append(e)
    return uniq


def parse_train_status_html(html_text: str) -> dict[str, Any]:
    raw_lines = extract_status_lines(html_text)
    lines = [_clean_line(r) for r in raw_lines]

    # Split into blocks by Start Date
    blocks: list[dict[str, Any]] = []
    current_block: dict[str, Any] | None = None

    for ln in lines:
        m = re.search(r"Start Date\s*:\s*(?P<date>\d{1,2}-[A-Za-z]{3}-\d{4})", ln, flags=re.I)
        if m:
            if current_block is not None:
                blocks.append(current_block)
            current_block = {"start_date": m.group("date"), "lines": [ln]}
        else:
            if current_block is not None:
                current_block["lines"].append(ln)

    if current_block is not None:
        blocks.append(current_block)

    # Build rich block data
    today = datetime.now().date()
    today_formatted = today.strftime("%d-%b-%Y")

    instances: list[dict[str, Any]] = []
    for block in blocks:
        block_lines = block["lines"]
        last_update_dt = _parse_last_update_dt(block_lines)
        status = _detect_status(block_lines)
        events = _parse_events(block_lines, last_update_dt)

        # Parse the block date
        try:
            block_date = datetime.strptime(block["start_date"], "%d-%b-%Y").date()
        except Exception:
            block_date = None

        instances.append({
            "start_date": block["start_date"],
            "status": status,           # running / completed / scheduled / unknown
            "is_today": block_date == today if block_date else False,
            "last_update": last_update_dt,
            "events": events,
        })

    # Sort: today first, then by date descending
    instances.sort(key=lambda x: (
        0 if x["is_today"] else 1,
        x["start_date"] or ""
    ), reverse=False)

    # Pick the primary instance to highlight
    # Priority: today running > today scheduled > today completed > most recent
    primary = None
    for inst in instances:
        if inst["is_today"] and inst["status"] == "running":
            primary = inst
            break
    if not primary:
        for inst in instances:
            if inst["is_today"] and inst["status"] == "scheduled":
                primary = inst
                break
    if not primary:
        for inst in instances:
            if inst["is_today"]:
                primary = inst
                break
    if not primary and instances:
        primary = instances[0]

    return {
        "start_date": primary["start_date"] if primary else None,
        "last_update": primary["last_update"] if primary else None,
        "events": primary["events"] if primary else [],
        "status": primary["status"] if primary else "unknown",
        "instances": instances,  # ALL instances for the app to display
    }