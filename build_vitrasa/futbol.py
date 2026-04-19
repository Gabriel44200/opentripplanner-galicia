# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""
Generates a GTFS feed for post-football match transit routes.

Match days are defined in a JSON file with the following format:
[
    { "date": "20260412", "match_start": "18:00" },
    ...
]

For each match day, two trips are generated per template route:
- Trip A: starts 2h00 after match_start
- Trip B: starts 2h10 after match_start

The template trips in futbol/trips.txt use relative time offsets from
00:00:00, which are added on top of the calculated departure base time.
"""

from argparse import ArgumentParser
import csv
import io
import json
import logging
import os
import zipfile
from datetime import datetime, timedelta


FUTBOL_DIR = os.path.join(os.path.dirname(__file__), "futbol")


# Default wave offsets after match start
DEFAULT_OFFSETS = [
    timedelta(hours=2, minutes=0),
    timedelta(hours=2, minutes=10),
]


def read_csv(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []
        reader.fieldnames = [name.strip() for name in reader.fieldnames]
        return [row for row in reader]


def time_to_delta(time_str: str) -> timedelta:
    """Parse a GTFS time string (HH:MM:SS) into a timedelta. Handles times >= 24:00:00."""
    parts = time_str.strip().split(":")
    h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    return timedelta(hours=h, minutes=m, seconds=s)


def delta_to_time(delta: timedelta) -> str:
    """Format a timedelta as a GTFS time string (HH:MM:SS). Supports hours >= 24."""
    total_seconds = int(delta.total_seconds())
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def write_csv(out: io.StringIO, rows: list[dict], fieldnames: list[str]) -> None:
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


def build_futbol_data(
    match_days_path: str,
    wave_offsets: list[timedelta] | None = None,
) -> dict[str, list[dict]]:
    """
    Generate futbol trip data from a match days JSON file.

    Returns a dict with keys: routes, shapes, trips, stop_times, calendar_dates.
    Does NOT include agency or stops — those are shared with the main feed.
    """
    if wave_offsets is None:
        wave_offsets = DEFAULT_OFFSETS

    with open(match_days_path, "r", encoding="utf-8") as f:
        match_days: list[dict] = json.load(f)
    logging.info(f"[futbol] Loaded {len(match_days)} match day(s).")

    template_trips = read_csv(os.path.join(FUTBOL_DIR, "trips.txt"))
    template_stop_times = read_csv(os.path.join(FUTBOL_DIR, "stop_times.txt"))

    stop_times_by_trip: dict[str, list[dict]] = {}
    for st in template_stop_times:
        tid = st["trip_id"].strip()
        stop_times_by_trip.setdefault(tid, []).append(st)
    for tid in stop_times_by_trip:
        stop_times_by_trip[tid].sort(key=lambda x: int(x["stop_sequence"].strip()))

    gen_trips: list[dict] = []
    gen_stop_times: list[dict] = []
    gen_calendar_dates: list[dict] = []

    for match in match_days:
        date_str: str = match["date"]
        match_start_str: str = match["match_start"]

        try:
            match_start_dt = datetime.strptime(match_start_str, "%H:%M")
        except ValueError:
            match_start_dt = datetime.strptime(match_start_str, "%H:%M:%S")

        match_start_delta = timedelta(
            hours=match_start_dt.hour,
            minutes=match_start_dt.minute,
            seconds=match_start_dt.second,
        )

        for wave_idx, offset in enumerate(wave_offsets):
            base_departure = match_start_delta + offset
            wave_label = f"w{wave_idx}"

            for tmpl_trip in template_trips:
                tmpl_id = tmpl_trip["trip_id"].strip()
                service_id = f"futbol_{date_str}_{tmpl_id}_{wave_label}"
                trip_id = service_id

                new_trip = dict(tmpl_trip)
                new_trip["trip_id"] = trip_id
                new_trip["service_id"] = service_id
                gen_trips.append(new_trip)

                for st in stop_times_by_trip.get(tmpl_id, []):
                    new_st = dict(st)
                    new_st["trip_id"] = trip_id
                    new_st["arrival_time"] = delta_to_time(
                        base_departure + time_to_delta(st["arrival_time"])
                    )
                    new_st["departure_time"] = delta_to_time(
                        base_departure + time_to_delta(st["departure_time"])
                    )
                    gen_stop_times.append(new_st)

                gen_calendar_dates.append({
                    "service_id": service_id,
                    "date": date_str,
                    "exception_type": "1",
                })

        logging.info(
            f"[futbol] Match {date_str} @ {match_start_str}: generated "
            f"{len(template_trips) * len(wave_offsets)} trip(s)."
        )

    logging.info(
        f"[futbol] Total: {len(gen_trips)} trips, {len(gen_stop_times)} stop time rows, "
        f"{len(gen_calendar_dates)} calendar_dates entries."
    )

    return {
        "routes": read_csv(os.path.join(FUTBOL_DIR, "routes.txt")),
        "shapes": read_csv(os.path.join(FUTBOL_DIR, "shapes.txt")),
        "trips": gen_trips,
        "stop_times": gen_stop_times,
        "calendar_dates": gen_calendar_dates,
    }


def generate_futbol_gtfs(
    match_days_path: str,
    output_path: str,
    wave_offsets: list[timedelta] | None = None,
) -> None:
    """Standalone wrapper: writes a complete self-contained GTFS ZIP."""
    data = build_futbol_data(match_days_path, wave_offsets)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # agency and stops are included here for a valid standalone feed
        for filename in ("agency.txt", "stops.txt"):
            src = os.path.join(FUTBOL_DIR, filename)
            if os.path.exists(src):
                zf.write(src, filename)

        for filename, rows in data.items():
            if not rows:
                continue
            buf = io.StringIO()
            write_csv(buf, rows, list(rows[0].keys()))
            zf.writestr(f"{filename}.txt", buf.getvalue())

    logging.info(f"[futbol] Output written to {output_path}.")


if __name__ == "__main__":
    parser = ArgumentParser(
        description="Generate GTFS feed for post-football match transit routes."
    )
    parser.add_argument(
        "match_days",
        type=str,
        help="Path to JSON file defining match days and start times.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "gtfs_vitrasa_futbol.zip"),
        help="Output GTFS ZIP file path.",
    )
    parser.add_argument(
        "--offset-minutes",
        type=int,
        nargs="+",
        default=None,
        metavar="MINUTES",
        help="Override default wave offsets in minutes after match start. Default: 120 130.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    wave_offsets = (
        [timedelta(minutes=m) for m in args.offset_minutes]
        if args.offset_minutes is not None
        else None
    )

    generate_futbol_gtfs(args.match_days, args.output, wave_offsets)
