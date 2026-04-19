# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""
Generates a GTFS feed for events transit routes (soccer, basket, concert).
Service IDs: FUT1 for soccer, COL1 for others.
"""

from argparse import ArgumentParser
import csv
import io
import json
import logging
import os
import zipfile
from datetime import datetime, timedelta

TWEAKS_DIR = os.path.join(os.path.dirname(__file__), "tweaks")

# Configuración de lógica por tipo de evento
EVENT_CONFIG = {
    "soccer": {
        "service_id": "FUT1",
        "pre": {"trip_id": "400040", "start_offset_min": -140, "end_offset_min": -20, "frequency_min": 20},
        "post": {"trip_id": "400140", "offsets_min": [130, 140]}
    },
    "basket": {
        "service_id": "COL1",
        "pre": {"trip_id": "245233", "start_offset_min": -95, "end_offset_min": -11, "frequency_min": 12},
        "post": {"trip_id": "245433", "offsets_min": [155, 165]}
    },
    "concert": {
        "service_id": "COL1",
        "pre": {"trip_id": "245233", "start_offset_min": -115, "end_offset_min": -15, "frequency_min": 20},
        "post": {"trip_id": "245433", "use_end_time": True, "offsets_min": [20]}
    }
}

def read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []
        reader.fieldnames = [name.strip() for name in reader.fieldnames]
        return [row for row in reader]

def parse_gtfs_time(time_str: str) -> timedelta:
    """Convierte HH:MM o HH:MM:SS (incluso > 24h) en un timedelta."""
    parts = time_str.strip().split(":")
    h = int(parts[0])
    m = int(parts[1])
    s = int(parts[2]) if len(parts) > 2 else 0
    return timedelta(hours=h, minutes=m, seconds=s)

def delta_to_time(delta: timedelta) -> str:
    """Formatea un timedelta como HH:MM:SS para GTFS."""
    total_seconds = int(delta.total_seconds())
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def write_csv(out: io.StringIO, rows: list[dict], fieldnames: list[str]) -> None:
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

def build_event_data(events_json_path: str) -> dict[str, list[dict]]:
    with open(events_json_path, "r", encoding="utf-8") as f:
        events: list[dict] = json.load(f)

    template_trips = read_csv(os.path.join(TWEAKS_DIR, "trips.txt"))
    template_stop_times = read_csv(os.path.join(TWEAKS_DIR, "stop_times.txt"))

    trips_templates = {t["trip_id"].strip(): t for t in template_trips}
    stop_times_by_trip: dict[str, list[dict]] = {}
    for st in template_stop_times:
        tid = st["trip_id"].strip()
        stop_times_by_trip.setdefault(tid, []).append(st)

    gen_trips: list[dict] = []
    gen_stop_times: list[dict] = []
    gen_calendar_dates: list[dict] = []
    
    # Para evitar duplicados en calendar_dates (un service_id activo en una fecha)
    seen_calendar = set()

    def add_expedition(base_trip_id: str, departure_delta: timedelta, date_str: str, service_id: str):
        if base_trip_id not in trips_templates:
            return

        # Generar HHMM para el trip_id (ej: 4000401815)
        total_sec = int(departure_delta.total_seconds())
        h = total_sec // 3600
        m = (total_sec % 3600) // 60
        time_hhmm = f"{h:02d}{m:02d}"
        
        trip_id = f"{base_trip_id}{time_hhmm}"

        # Crear viaje
        new_trip = dict(trips_templates[base_trip_id])
        new_trip["trip_id"] = trip_id
        new_trip["service_id"] = service_id
        gen_trips.append(new_trip)

        # Crear stop_times
        for st in stop_times_by_trip.get(base_trip_id, []):
            new_st = dict(st)
            new_st["trip_id"] = trip_id
            tmpl_arrival_offset = parse_gtfs_time(st["arrival_time"])
            tmpl_departure_offset = parse_gtfs_time(st["departure_time"])
            
            new_st["arrival_time"] = delta_to_time(departure_delta + tmpl_arrival_offset)
            new_st["departure_time"] = delta_to_time(departure_delta + tmpl_departure_offset)
            gen_stop_times.append(new_st)

        # Añadir a calendar_dates si no se ha registrado esa combinación
        cal_key = (service_id, date_str)
        if cal_key not in seen_calendar:
            gen_calendar_dates.append({
                "service_id": service_id,
                "date": date_str,
                "exception_type": "1",
            })
            seen_calendar.add(cal_key)

    for event in events:
        etype = event.get("type", "soccer")
        config = EVENT_CONFIG.get(etype)
        if not config:
            continue

        date_str = event["date"]
        service_id = config["service_id"]
        start_delta = parse_gtfs_time(event["start_time"])

        # --- PRE-EVENTO ---
        pre = config["pre"]
        curr_offset = pre["start_offset_min"]
        while curr_offset <= pre["end_offset_min"]:
            dep_delta = start_delta + timedelta(minutes=curr_offset)
            add_expedition(pre["trip_id"], dep_delta, date_str, service_id)
            curr_offset += pre["frequency_min"]

        # --- POST-EVENTO ---
        post = config["post"]
        if post.get("use_end_time") and "end_time" in event:
            base_delta = parse_gtfs_time(event["end_time"])
        else:
            base_delta = start_delta

        for offset in post["offsets_min"]:
            dep_delta = base_delta + timedelta(minutes=offset)
            add_expedition(post["trip_id"], dep_delta, date_str, service_id)

    return {
        "routes": read_csv(os.path.join(TWEAKS_DIR, "routes.txt")),
        "shapes": read_csv(os.path.join(TWEAKS_DIR, "shapes.txt")),
        "trips": gen_trips,
        "stop_times": gen_stop_times,
        "calendar_dates": gen_calendar_dates,
    }

def generate_gtfs(events_json: str, output_path: str):
    data = build_event_data(events_json)
    
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename in ("agency.txt", "stops.txt"):
            src = os.path.join(TWEAKS_DIR, filename)
            if os.path.exists(src):
                zf.write(src, filename)

        for filename, rows in data.items():
            if not rows: continue
            buf = io.StringIO()
            write_csv(buf, rows, list(rows[0].keys()))
            zf.writestr(f"{filename}.txt", buf.getvalue())

    logging.info(f"GTFS generado con {len(data['trips'])} viajes en: {output_path}")

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("events_json")
    parser.add_argument("--output", default="gtfs_eventos.zip")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    generate_gtfs(args.events_json, args.output)