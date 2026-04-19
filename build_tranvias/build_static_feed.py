# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "requests"
# ]
# ///

from argparse import ArgumentParser
import csv
import json
import logging
import os
import shutil
import tempfile
import zipfile
import sys
from datetime import datetime, timedelta

import requests

FEED_ID = 1574

def get_rows(input_file: str) -> list[dict]:
    rows: list[dict] = []
    if not os.path.exists(input_file):
        return []
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
    parser.add_argument("nap_apikey", type=str, help="NAP API Key")
    parser.add_argument("--events", type=str, default=None, help="JSON con eventos (futbol, basket, etc.)")
    parser.add_argument("--debug", help="Enable debug logging", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    INPUT_GTFS_FD, INPUT_GTFS_ZIP = tempfile.mkstemp(suffix=".zip", prefix="coruna_in_")
    INPUT_GTFS_PATH = tempfile.mkdtemp(prefix="coruna_in_")
    OUTPUT_GTFS_PATH = tempfile.mkdtemp(prefix="coruna_out_")
    OUTPUT_GTFS_ZIP = os.path.join(os.path.dirname(__file__), "gtfs_coruna.zip")

    FEED_URL = f"https://nap.transportes.gob.es/api/Fichero/download/{FEED_ID}"

    logging.info(f"Downloading GTFS feed '{FEED_ID}'...")
    response = requests.get(FEED_URL, headers={"ApiKey": args.nap_apikey})
    with open(INPUT_GTFS_ZIP, "wb") as f:
        f.write(response.content)

    with zipfile.ZipFile(INPUT_GTFS_ZIP, "r") as zip_ref:
        zip_ref.extractall(INPUT_GTFS_PATH)

    # Rutas de archivos base
    TRIPS_FILE = os.path.join(INPUT_GTFS_PATH, "trips.txt")
    STOPS_FILE = os.path.join(INPUT_GTFS_PATH, "stops.txt")
    ROUTES_FILE = os.path.join(INPUT_GTFS_PATH, "routes.txt")
    CALENDAR_FILE = os.path.join(INPUT_GTFS_PATH, "calendar.txt")
    CALENDAR_DATES_FILE = os.path.join(INPUT_GTFS_PATH, "calendar_dates.txt")

    # Copiar archivos base que NO vamos a procesar manualmente
    for filename in os.listdir(INPUT_GTFS_PATH):
        if filename in ["stops.txt", "routes.txt", "trips.txt", "calendar.txt", "calendar_dates.txt", "stop_times.txt", "shapes.txt"] or not filename.endswith(".txt"):
            continue
        shutil.copy(os.path.join(INPUT_GTFS_PATH, filename), os.path.join(OUTPUT_GTFS_PATH, filename))

    # --- PROCESAR TRIPS ---
    logging.info("Processing trips.txt...")
    overrides_path = os.path.join(os.path.dirname(__file__), "trip_byshape_overrides.json")
    trip_overrides = {}
    if os.path.exists(overrides_path):
        with open(overrides_path, "r", encoding="utf-8") as f:
            trip_overrides = {item["shape_id"]: item for item in json.load(f)}
    
    trips = get_rows(TRIPS_FILE)
    for trip in trips:
        tsid = trip.get("shape_id")
        if tsid in trip_overrides:
            trip.update(trip_overrides[tsid])

    # --- PROCESAR STOPS ---
    logging.info("Processing stops.txt...")
    stop_overrides_path = os.path.join(os.path.dirname(__file__), "stop_overrides.json")
    stop_overrides = {}
    if os.path.exists(stop_overrides_path):
        with open(stop_overrides_path, "r", encoding="utf-8") as f:
            stop_overrides = {item["stop_id"]: item for item in json.load(f)}
    
    stops = get_rows(STOPS_FILE)
    for stop in stops:
        if stop.get("stop_desc"): stop["stop_name"] = stop["stop_desc"]
        sid = stop.get("stop_id")
        if sid in stop_overrides: stop.update(stop_overrides[sid])

    # --- PROCESAR ROUTES ---
    logging.info("Processing routes.txt...")
    route_overrides_path = os.path.join(os.path.dirname(__file__), "route_overrides.json")
    route_overrides = {}
    if os.path.exists(route_overrides_path):
        with open(route_overrides_path, "r", encoding="utf-8") as f:
            route_overrides = {item["route_id"]: item for item in json.load(f)}
    
    routes = get_rows(ROUTES_FILE)
    for route in routes:
        rid = route.get("route_id")
        if rid in route_overrides: route.update(route_overrides[rid])

    # --- PROCESAR CALENDAR (BUI fix) ---
    logging.info("Processing calendar.txt...")
    current_year = datetime.now().year
    calendars = get_rows(CALENDAR_FILE)
    for cal in calendars:
        if cal["service_id"][:-6] == "1801":
            cal["start_date"] = f"{current_year}0801"
            cal["end_date"] = f"{current_year}0831"

    # --- PROCESAR CALENDAR_DATES (BUI fix) ---
    logging.info("Processing calendar_dates.txt...")
    calendar_dates = [d for d in get_rows(CALENDAR_DATES_FILE) if d["service_id"][:-6] != "1801"]

    # --- LEER STOP_TIMES Y SHAPES ORIGINALES ---
    stop_times = get_rows(os.path.join(INPUT_GTFS_PATH, "stop_times.txt"))
    shapes = get_rows(os.path.join(INPUT_GTFS_PATH, "shapes.txt"))

    # --- INTEGRACIÓN DE EVENTOS (FÚTBOL, BASKET, CONCERT) ---
    if args.events:
        logging.info(f"Merging events from {args.events}...")
        sys.path.insert(0, os.path.dirname(__file__))
        try:
            from futbol import build_event_data
            event_data = build_event_data(args.events)

            # Fusionar listas
            routes.extend(event_data.get("routes", []))
            trips.extend(event_data.get("trips", []))
            calendar_dates.extend(event_data.get("calendar_dates", []))
            stop_times.extend(event_data.get("stop_times", []))
            shapes.extend(event_data.get("shapes", []))
            
            logging.info(f"Events merged: {len(event_data.get('trips', []))} trips added.")
        except ImportError:
            logging.error("No se pudo encontrar futbol.py en el mismo directorio.")
        except Exception as e:
            logging.error(f"Error procesando eventos: {e}")

    # --- ESCRITURA DE ARCHIVOS FINALES ---
    # Usamos fieldnames basados en el primer elemento de cada lista, 
    # pero extrasaction="ignore" para descartar columnas que no existan en el feed base
    files_to_write = {
        "trips.txt": trips,
        "stops.txt": stops,
        "routes.txt": routes,
        "calendar.txt": calendars,
        "calendar_dates.txt": calendar_dates,
        "stop_times.txt": stop_times,
        "shapes.txt": shapes
    }

    for name, data in files_to_write.items():
        if not data:
            continue
        
        output_file = os.path.join(OUTPUT_GTFS_PATH, name)
        # IMPORTANTE: Definimos las columnas basadas en el archivo original (primera fila)
        # para que el GTFS final sea coherente con la estructura de Coruña.
        fieldnames = list(data[0].keys())
        
        with open(output_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data)

    # --- CREAR ZIP FINAL ---
    with zipfile.ZipFile(OUTPUT_GTFS_ZIP, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(OUTPUT_GTFS_PATH):
            for file in files:
                zipf.write(os.path.join(root, file), file)

    logging.info(f"GTFS generado con éxito en {OUTPUT_GTFS_ZIP}")
    
    # Limpieza de temporales
    os.close(INPUT_GTFS_FD)
    os.remove(INPUT_GTFS_ZIP)
    shutil.rmtree(INPUT_GTFS_PATH)
    shutil.rmtree(OUTPUT_GTFS_PATH)