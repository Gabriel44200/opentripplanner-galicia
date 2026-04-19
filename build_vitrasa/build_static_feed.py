# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "requests"
# ]
# ///

from argparse import ArgumentParser
import csv
from datetime import date, datetime, timedelta
import json
import logging
import os
import shutil
import sys
import tempfile
import zipfile

import requests


def get_rows(input_file: str) -> list[dict]:
    rows: list[dict] = []

    with open(input_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []
        reader.fieldnames = [name.strip() for name in reader.fieldnames]

        for row in reader:
            rows.append(row)

    return rows


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--debug",
        help="Enable debug logging",
        action="store_true"
    )
    parser.add_argument(
        "--match-days",
        type=str,
        default=None,
        metavar="FILE",
        help="Path to JSON file with football match days. If provided, futbol routes/trips are merged into gtfs_vigo.zip.",
    )
    parser.add_argument(
        "--futbol-offset-minutes",
        type=int,
        nargs="+",
        default=None,
        metavar="MINUTES",
        help="Wave offsets in minutes after match start for the futbol feed. Default: 120 130.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    INPUT_GTFS_FD, INPUT_GTFS_ZIP = tempfile.mkstemp(suffix=".zip", prefix="vigo_in_")
    INPUT_GTFS_PATH = tempfile.mkdtemp(prefix="vigo_in_")
    OUTPUT_GTFS_PATH = tempfile.mkdtemp(prefix="vigo_out_")
    OUTPUT_GTFS_ZIP = os.path.join(os.path.dirname(__file__), "gtfs_vigo.zip")

    FEED_URL = f"https://datos.vigo.org/data/transporte/gtfs_vigo.zip"

    logging.info(f"Downloading GTFS feed from '{FEED_URL}'...")
    response = requests.get(FEED_URL)
    with open(INPUT_GTFS_ZIP, "wb") as f:
        f.write(response.content)

    # Unzip the GTFS feed
    with zipfile.ZipFile(INPUT_GTFS_ZIP, "r") as zip_ref:
        zip_ref.extractall(INPUT_GTFS_PATH)

    TRIPS_FILE = os.path.join(INPUT_GTFS_PATH, "trips.txt")
    STOPS_FILE = os.path.join(INPUT_GTFS_PATH, "stops.txt")
    ROUTES_FILE = os.path.join(INPUT_GTFS_PATH, "routes.txt")

    # Build calendar.txt from calendar_dates.txt
    # infer each service's weekly pattern from which actual dates it ran on.
    # The "reference weekday" is the weekday date with the most active services
    # (i.e. the most likely normal working day, avoiding holidays).
    # Saturday and Sunday services are inferred from the Saturday/Sunday dates present.
    CALENDAR_DATES_FILE = os.path.join(INPUT_GTFS_PATH, "calendar_dates.txt")

    # service_id -> set of YYYYMMDD date strings (exception_type=1 only)
    service_dates: dict[str, set[str]] = {}
    for row in get_rows(CALENDAR_DATES_FILE):
        if row.get("exception_type", "").strip() != "1":
            continue
        sid = row["service_id"].strip()
        d = row["date"].strip()
        service_dates.setdefault(sid, set()).add(d)

    logging.debug(f"Found {len(service_dates)} service IDs in calendar_dates.txt")

    def _parse_date(d: str) -> date:
        return datetime.strptime(d, "%Y%m%d").date()

    all_dates: set[str] = {d for dates in service_dates.values() for d in dates}

    # Group dates by day-of-week (0=Mon … 6=Sun)
    dates_by_dow: dict[int, list[str]] = {}
    for d in all_dates:
        dow = _parse_date(d).weekday()
        dates_by_dow.setdefault(dow, []).append(d)

    saturday_dates: set[str] = set(dates_by_dow.get(5, []))
    sunday_dates:   set[str] = set(dates_by_dow.get(6, []))
    weekday_dates:  set[str] = set()
    for _dow in range(5):
        weekday_dates.update(dates_by_dow.get(_dow, []))

    # Pick the weekday date where the most services run (most "normal" working day).
    # Days with fewer services than others are likely public holidays.
    weekday_svc_counts: dict[str, int] = {
        d: sum(1 for dates in service_dates.values() if d in dates)
        for d in weekday_dates
    }
    if weekday_svc_counts:
        ref_weekday = max(weekday_svc_counts, key=weekday_svc_counts.__getitem__)
        logging.info(
            f"Reference weekday: {ref_weekday} "
            f"({_parse_date(ref_weekday).strftime('%A')}) "
            f"with {weekday_svc_counts[ref_weekday]} active services"
        )
    else:
        ref_weekday = None
        logging.warning("No weekday dates found in calendar_dates.txt")

    # ── Holiday exceptions ──────────────────────────────────────────────────
    # Known public holidays (YYYYMMDD). For weekday holidays:
    #   • exception_type=2 for weekday services that don't actually run that day
    #   • exception_type=1 for holiday services that do run (not in calendar.txt)
    HOLIDAY_DATES: set[str] = {
        "20260101", "20260106", "20260319",
        "20260328", "20260402", "20260403",
        "20260501", "20260624", "20260817",
        "20261012", "20261208", "20261225",
    }

    feed_start = min(_parse_date(d) for d in all_dates)
    feed_end   = feed_start + timedelta(days=365)

    # Services that can't be classified as weekday/Saturday/Sunday (e.g. holiday-only
    # services that never ran on the reference weekday or a weekend) are preserved
    # verbatim via calendar_dates.txt rather than being dropped.
    non_holiday_weekday_dates = weekday_dates - HOLIDAY_DATES
    non_holiday_saturday_dates = saturday_dates - HOLIDAY_DATES
    unclassified_service_dates: dict[str, set[str]] = {}

    calendar_output_rows: list[dict] = []
    added_services = set()

    for sid, dates in service_dates.items():
        is_weekday  = bool(dates & non_holiday_weekday_dates)
        is_saturday = bool(dates & non_holiday_saturday_dates)
        is_sunday   = bool(dates & sunday_dates)

        if not is_weekday and not is_saturday and not is_sunday:
            logging.info(
                "Service %r has no day-type classification; "
                "will preserve its %d date(s) in calendar_dates.txt",
                sid, len(dates),
            )
            unclassified_service_dates[sid] = dates
            continue

        wd  = "1" if is_weekday  else "0"
        sat = "1" if is_saturday else "0"
        sun = "1" if is_sunday   else "0"

        comparing_string = f"{sid[-6:]}__{wd}{sat}{sun}"
        if comparing_string in added_services:
            logging.warning(
                "Service %r has the same day pattern as another service, skipping",
                sid
            )
            continue
        added_services.add(comparing_string)

        calendar_output_rows.append({
            "service_id": sid,
            "monday":     wd,
            "tuesday":    wd,
            "wednesday":  wd,
            "thursday":   wd,
            "friday":     wd,
            "saturday":   sat,
            "sunday":     sun,
            # 2 days before feed start, so feeds published early don't mess it up
            "start_date": (feed_start - timedelta(days=2)).strftime("%Y%m%d"),
            "end_date":   feed_end.strftime("%Y%m%d"),
        })

    logging.info(f"Generated {len(calendar_output_rows)} calendar.txt entries")

    weekday_holiday_dates = sorted(
        d for d in HOLIDAY_DATES
        if _parse_date(d).weekday() < 5
        and feed_start <= _parse_date(d) <= feed_end
    )
    logging.info(
        "Weekday holidays within feed range: %s",
        ", ".join(_parse_date(d).strftime("%Y-%m-%d (%a)") for d in weekday_holiday_dates),
    )

    weekday_service_ids = {
        row["service_id"] for row in calendar_output_rows if row["monday"] == "1"
    }

    # Preserve all dates of unclassified (holiday-only) services verbatim.
    calendar_dates_output_rows: list[dict] = [
        {"service_id": sid, "date": d, "exception_type": "1"}
        for sid, dates in unclassified_service_dates.items()
        for d in sorted(dates)
    ]
    logging.info(
        "Preserved %d calendar_dates.txt entries for %d unclassified services.",
        len(calendar_dates_output_rows), len(unclassified_service_dates),
    )

    for holiday_date in weekday_holiday_dates:
        services_on_holiday = {
            sid for sid, dates in service_dates.items() if holiday_date in dates
        }
        # Suppress weekday services that do NOT actually operate on this holiday
        removed = 0
        for sid in weekday_service_ids:
            if sid not in services_on_holiday:
                calendar_dates_output_rows.append(
                    {"service_id": sid, "date": holiday_date, "exception_type": "2"}
                )
                removed += 1
        logging.debug(
            "Holiday %s: suppressed %d weekday services",
            holiday_date, removed,
        )

    logging.info(
        "Generated %d total calendar_dates.txt entries (%d weekday holidays processed).",
        len(calendar_dates_output_rows), len(weekday_holiday_dates),
    )

    # Copy every file in the feed except calendar_dates.txt / calendar.txt
    # (we replace them with a freshly generated calendar.txt above)
    for filename in os.listdir(INPUT_GTFS_PATH):
        if not filename.endswith(".txt"):
            continue
        if filename in ("calendar_dates.txt", "calendar.txt"):
            continue

        src_path = os.path.join(INPUT_GTFS_PATH, filename)
        dest_path = os.path.join(OUTPUT_GTFS_PATH, filename)
        shutil.copy(src_path, dest_path)

    CALENDAR_OUTPUT_FILE = os.path.join(OUTPUT_GTFS_PATH, "calendar.txt")
    with open(CALENDAR_OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "service_id", "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday", "start_date", "end_date",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(calendar_output_rows)

    CALENDAR_DATES_OUTPUT_FILE = os.path.join(OUTPUT_GTFS_PATH, "calendar_dates.txt")
    with open(CALENDAR_DATES_OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["service_id", "date", "exception_type"])
        writer.writeheader()
        writer.writerows(calendar_dates_output_rows)

    if args.match_days is not None:
        sys.path.insert(0, os.path.dirname(__file__))
        from futbol import build_futbol_data
        from datetime import timedelta as _td

        wave_offsets = (
            [_td(minutes=m) for m in args.futbol_offset_minutes]
            if args.futbol_offset_minutes is not None
            else None
        )
        futbol = build_futbol_data(args.match_days, wave_offsets)

        # Append futbol routes to routes.txt
        routes_file = os.path.join(OUTPUT_GTFS_PATH, "routes.txt")
        with open(routes_file, "r", encoding="utf-8", newline="") as f:
            routes_fieldnames = next(csv.reader(f))
        with open(routes_file, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=routes_fieldnames, extrasaction="ignore")
            writer.writerows(futbol["routes"])

        # Append futbol shapes to shapes.txt (create if missing)
        if futbol["shapes"]:
            shapes_file = os.path.join(OUTPUT_GTFS_PATH, "shapes.txt")
            file_exists = os.path.exists(shapes_file)
            if file_exists:
                with open(shapes_file, "r", encoding="utf-8", newline="") as f:
                    shapes_fieldnames = next(csv.reader(f))
            else:
                shapes_fieldnames = list(futbol["shapes"][0].keys())
            with open(shapes_file, "a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=shapes_fieldnames, extrasaction="ignore")
                if not file_exists:
                    writer.writeheader()
                writer.writerows(futbol["shapes"])

        # Append futbol trips to trips.txt
        trips_file = os.path.join(OUTPUT_GTFS_PATH, "trips.txt")
        with open(trips_file, "r", encoding="utf-8", newline="") as f:
            trips_fieldnames = next(csv.reader(f))
        with open(trips_file, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=trips_fieldnames, extrasaction="ignore")
            writer.writerows(futbol["trips"])

        # Append futbol stop_times to stop_times.txt
        stoptimes_file = os.path.join(OUTPUT_GTFS_PATH, "stop_times.txt")
        with open(stoptimes_file, "r", encoding="utf-8", newline="") as f:
            stoptimes_fieldnames = next(csv.reader(f))
        with open(stoptimes_file, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=stoptimes_fieldnames, extrasaction="ignore")
            writer.writerows(futbol["stop_times"])

        # Append futbol calendar_dates entries
        with open(CALENDAR_DATES_OUTPUT_FILE, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["service_id", "date", "exception_type"])
            writer.writerows(futbol["calendar_dates"])

        logging.info("[futbol] Data merged into main feed.")

    # Create a ZIP archive of the output GTFS
    with zipfile.ZipFile(OUTPUT_GTFS_ZIP, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(OUTPUT_GTFS_PATH):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, OUTPUT_GTFS_PATH)
                zipf.write(file_path, arcname)

    logging.info(
        f"GTFS data from feed has been zipped successfully at {OUTPUT_GTFS_ZIP}."
    )
    os.close(INPUT_GTFS_FD)
    os.remove(INPUT_GTFS_ZIP)
    shutil.rmtree(INPUT_GTFS_PATH)
    shutil.rmtree(OUTPUT_GTFS_PATH)
