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

import requests


FEED_ID = 1574


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
        "nap_apikey",
        type=str,
        help="NAP API Key (https://nap.transportes.gob.es/)"
    )
    parser.add_argument(
        "--debug",
        help="Enable debug logging",
        action="store_true"
    )

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

    # Unzip the GTFS feed
    with zipfile.ZipFile(INPUT_GTFS_ZIP, "r") as zip_ref:
        zip_ref.extractall(INPUT_GTFS_PATH)

    TRIPS_FILE = os.path.join(INPUT_GTFS_PATH, "trips.txt")
    STOPS_FILE = os.path.join(INPUT_GTFS_PATH, "stops.txt")
    ROUTES_FILE = os.path.join(INPUT_GTFS_PATH, "routes.txt")

    # Copy every file in feed except stops.txt and routes.txt
    for filename in os.listdir(INPUT_GTFS_PATH):
        if filename in ["stops.txt", "routes.txt"]:
            continue
        if not filename.endswith(".txt"):
            continue

        src_path = os.path.join(INPUT_GTFS_PATH, filename)
        dest_path = os.path.join(OUTPUT_GTFS_PATH, filename)
        shutil.copy(src_path, dest_path)

    # Process trips.txt
    logging.info("Processing trips.txt...")
    with open(
        os.path.join(os.path.dirname(__file__), "trip_byshape_overrides.json"),
        "r",
        encoding="utf-8",
    ) as f:
        trip_byshape_overrides_list = json.load(f)
        trip_byshape_overrides = {item["shape_id"]: item for item in trip_byshape_overrides_list}

    trips = get_rows(TRIPS_FILE)
    for trip in trips:
        tsid = trip["shape_id"]

        # Then we apply the overrides (which could update the name too, that's why it's done later)
        if tsid in trip_byshape_overrides:
            for key, value in trip_byshape_overrides[tsid].items():
                trip[key] = value

    if trips:
        with open(
            os.path.join(OUTPUT_GTFS_PATH, "trips.txt"),
            "w",
            encoding="utf-8",
            newline="",
        ) as f:
            writer = csv.DictWriter(f, fieldnames=trips[0].keys())
            writer.writeheader()
            writer.writerows(trips)

    # Process stops.txt
    logging.info("Processing stops.txt...")
    with open(
        os.path.join(os.path.dirname(__file__), "stop_overrides.json"),
        "r",
        encoding="utf-8",
    ) as f:
        stop_overrides_list = json.load(f)
        stop_overrides = {item["stop_id"]: item for item in stop_overrides_list}

    stops = get_rows(STOPS_FILE)
    for stop in stops:
        sid = stop["stop_id"]

        # First we default the stop_name to stop_desc if it's not empty
        if stop["stop_desc"] != "":
            stop["stop_name"] = stop["stop_desc"]

        # Then we apply the overrides (which could update the name too, that's why it's done later)
        if sid in stop_overrides:
            for key, value in stop_overrides[sid].items():
                stop[key] = value

    if stops:
        with open(
            os.path.join(OUTPUT_GTFS_PATH, "stops.txt"),
            "w",
            encoding="utf-8",
            newline="",
        ) as f:
            writer = csv.DictWriter(f, fieldnames=stops[0].keys())
            writer.writeheader()
            writer.writerows(stops)

    # Process routes.txt
    logging.info("Processing routes.txt...")
    with open(
        os.path.join(os.path.dirname(__file__), "route_overrides.json"),
        "r",
        encoding="utf-8",
    ) as f:
        route_overrides_list = json.load(f)
        route_overrides = {item["route_id"]: item for item in route_overrides_list}

    routes = get_rows(ROUTES_FILE)
    for route in routes:
        rid = route["route_id"]
        if rid in route_overrides:
            for key, value in route_overrides[rid].items():
                route[key] = value

    if routes:
        with open(
            os.path.join(OUTPUT_GTFS_PATH, "routes.txt"),
            "w",
            encoding="utf-8",
            newline="",
        ) as f:
            writer = csv.DictWriter(f, fieldnames=routes[0].keys())
            writer.writeheader()
            writer.writerows(routes)

    # Create a ZIP archive of the output GTFS
    with zipfile.ZipFile(OUTPUT_GTFS_ZIP, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(OUTPUT_GTFS_PATH):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, OUTPUT_GTFS_PATH)
                zipf.write(file_path, arcname)

    logging.info(
        f"GTFS data from feed {FEED_ID} has been zipped successfully at {OUTPUT_GTFS_ZIP}."
    )
    os.close(INPUT_GTFS_FD)
    os.remove(INPUT_GTFS_ZIP)
    shutil.rmtree(INPUT_GTFS_PATH)
    shutil.rmtree(OUTPUT_GTFS_PATH)
