# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "requests",
#     "shapely",
#     "tqdm",
# ]
# ///

from argparse import ArgumentParser
from collections import defaultdict
import csv
import json
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import requests
from shapely.geometry import Point, shape
from shapely.strtree import STRtree
from tqdm import tqdm


def _load_boundaries(path: Path) -> tuple[
    dict[str, dict],        # muni_by_ine:      {ine_5 -> {shape, props}}
    dict[str, list[dict]],  # parishes_by_muni: {ine_5 -> [{shape, props}, ...]}
]:
    logging.info("Loading boundaries from %s …", path)
    with open(path, encoding="utf-8") as fh:
        geojson = json.load(fh)

    muni_by_ine: dict[str, dict] = {}
    parishes_by_muni: dict[str, list] = defaultdict(list)

    for feature in geojson["features"]:
        props = feature["properties"]
        geom = shape(feature["geometry"])
        level = props["admin_level"]
        ine_muni = props.get("ine_muni", "")

        if level == 8:
            if ine_muni:
                muni_by_ine[ine_muni] = {"shape": geom, "props": props}
        elif level == 9:
            ref_ine = props.get("ref_ine", "")
            parent_ine = ref_ine[:5] if ref_ine else ine_muni
            if parent_ine:
                parishes_by_muni[parent_ine].append({"shape": geom, "props": props})

    logging.info(
        "Loaded %d municipalities, %d parishes grouped into %d municipalities.",
        len(muni_by_ine),
        sum(len(v) for v in parishes_by_muni.values()),
        len(parishes_by_muni),
    )
    return muni_by_ine, dict(parishes_by_muni)


def _build_parish_trees(
    parishes_by_muni: dict[str, list[dict]],
) -> dict[str, tuple[STRtree, list[dict]]]:
    trees: dict[str, tuple[STRtree, list[dict]]] = {}
    for ine, parish_list in parishes_by_muni.items():
        geoms = [p["shape"] for p in parish_list]
        trees[ine] = (STRtree(geoms), parish_list)
    return trees


def _find_parish(
    point: Point,
    ine_muni: str,
    parish_trees: dict[str, tuple[STRtree, list[dict]]],
) -> dict | None:
    entry = parish_trees.get(ine_muni)
    if entry is None:
        return None
    tree, parish_list = entry
    hits = tree.query(point, predicate="intersects")
    if len(hits) == 0:
        return None
    if len(hits) == 1:
        return parish_list[hits[0]]["props"]
    best = min(hits, key=lambda i: parish_list[i]["shape"].centroid.distance(point))
    return parish_list[best]["props"]


def build_stop_desc(
    stop: dict,
    muni_by_ine: dict[str, dict],
    parish_trees: dict[str, tuple[STRtree, list[dict]]],
) -> str:
    """Return a stop_desc string of the form 'Parish (Municipality)', or an
    empty string if neither can be resolved."""
    zone_id = stop.get("zone_id", "")
    ine_muni = zone_id[:5] if len(zone_id) >= 5 else ""

    muni_entry = muni_by_ine.get(ine_muni) if ine_muni else None
    muni_name = muni_entry["props"]["name"] if muni_entry else ""

    try:
        lat = float(stop["stop_lat"])
        lon = float(stop["stop_lon"])
    except ValueError:
        return muni_name

    parish_props = _find_parish(Point(lon, lat), ine_muni, parish_trees)
    parish_name = parish_props["name"] if parish_props else ""

    if parish_name and muni_name:
        return f"{parish_name} -- {muni_name}"
    return parish_name or muni_name


if __name__ == "__main__":
    parser = ArgumentParser(
        description="Build static GTFS feed for Galicia (Xunta) with parish/municipality stop descriptions."
    )
    parser.add_argument(
        "nap_apikey",
        type=str,
        help="NAP API Key (https://nap.transportes.gob.es/)"
    )
    parser.add_argument(
        "--boundaries",
        type=Path,
        default=Path(os.path.join(os.path.dirname(__file__), "parroquias.geojson")),
        help="Path to the boundaries GeoJSON produced by gen_parroquias.py "
             "(default: parroquias.geojson next to this script).",
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

    # Boundaries
    muni_by_ine, parishes_by_muni = _load_boundaries(args.boundaries)
    logging.info("Building per-municipality parish trees …")
    parish_trees = _build_parish_trees(parishes_by_muni)

    # Download & unpack feed
    INPUT_GTFS_FD, INPUT_GTFS_ZIP = tempfile.mkstemp(suffix=".zip", prefix="xunta_in_")
    INPUT_GTFS_PATH = tempfile.mkdtemp(prefix="xunta_in_")
    OUTPUT_GTFS_PATH = tempfile.mkdtemp(prefix="xunta_out_")
    OUTPUT_GTFS_ZIP = os.path.join(os.path.dirname(__file__), "gtfs_xunta.zip")

    FEED_URL = "https://nap.transportes.gob.es/api/Fichero/download/1584"

    logging.info("Downloading GTFS feed...")
    response = requests.get(FEED_URL, headers={"ApiKey": args.nap_apikey})
    response.raise_for_status()
    with open(INPUT_GTFS_ZIP, "wb") as f:
        f.write(response.content)

    with zipfile.ZipFile(INPUT_GTFS_ZIP, "r") as zip_ref:
        zip_ref.extractall(INPUT_GTFS_PATH)

    STOPS_FILE = os.path.join(INPUT_GTFS_PATH, "stops.txt")
    STOP_TIMES_FILE = os.path.join(INPUT_GTFS_PATH, "stop_times.txt")
    TRIPS_FILE = os.path.join(INPUT_GTFS_PATH, "trips.txt")

    # Copy unchanged files
    for filename in ["trips.txt",
                     "calendar.txt", "calendar_dates.txt",
                     "shapes.txt"]:
        src = os.path.join(INPUT_GTFS_PATH, filename)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(OUTPUT_GTFS_PATH, filename))
        else:
            logging.debug("File %s not present in the input feed, skipping.", filename)

    # Load agency list
    AGENCY_MAPPINGS_JSON_FILE = Path(os.path.join(os.path.dirname(__file__), "agency_mappings.json"))
    with open(AGENCY_MAPPINGS_JSON_FILE, encoding="utf-8") as f:
        agency_mappings: dict[str, dict[str, str]] = json.load(f)

    with open(os.path.join(OUTPUT_GTFS_PATH, "agency.txt"), "w", encoding="utf-8", newline="") as agency_out:
        fieldnames = ["agency_id", "agency_name", "agency_url", "agency_email",
                        "agency_phone", "agency_timezone", "agency_lang"]
        writer = csv.DictWriter(agency_out, fieldnames=fieldnames)
        writer.writeheader()
        for agency_id, mapping in agency_mappings.items():
            writer.writerow({
                "agency_id": agency_id,
                "agency_name": mapping["agency_name"],
                "agency_url": mapping["agency_url"],
                "agency_email": mapping["agency_email"],
                "agency_phone": mapping["agency_phone"],
                "agency_timezone": "Europe/Madrid",
                "agency_lang": "es",
            })

    # Load routes, mapping to agency_id by first 5 chars of route_short_name, and apply route_color/route_text_color from the mapping if available
    with open(os.path.join(INPUT_GTFS_PATH, "routes.txt"), encoding="utf-8-sig", newline="") as routes_fh:
        reader = csv.DictReader(routes_fh)
        routes = list(reader)
        route_fieldnames = set(reader.fieldnames or routes[0].keys())

    for route in routes:
        short_name = route.get("route_short_name", "")
        agency_key = short_name[:5] if len(short_name) >= 5 else ""
        
        mapping = agency_mappings.get(agency_key, None)
        route["agency_id"] = agency_key if mapping else "unknown"
        if route["agency_id"] == "unknown":
            logging.error("Route %s: could not determine agency_id from route_short_name '%s'.", route["route_id"], short_name)
            continue
        if mapping is None:
            logging.error("Route %s: no agency mapping found for key '%s'.", route["route_id"], agency_key)
            continue

        if "route_color" in mapping:
            route["route_color"] = mapping["route_color"]
            route_fieldnames.add("route_color")
        if "route_text_color" in mapping:
            route["route_text_color"] = mapping["route_text_color"]
            route_fieldnames.add("route_text_color")
        
    with open(os.path.join(OUTPUT_GTFS_PATH, "routes.txt"), "w", encoding="utf-8", newline="") as routes_out:
        writer = csv.DictWriter(routes_out, fieldnames=route_fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(routes)

    # Build stops.txt with stop_desc
    logging.info("Enriching stops with parish/municipality descriptions …")
    with open(STOPS_FILE, encoding="utf-8-sig", newline="") as in_fh:
        reader = csv.DictReader(in_fh)
        stops = list(reader)
        base_fieldnames = list(reader.fieldnames or stops[0].keys())

    unmatched = 0
    for stop in tqdm(stops, desc="Enriching stops", unit="stop"):
        desc = build_stop_desc(stop, muni_by_ine, parish_trees)
        stop["stop_desc"] = desc
        if not desc:
            unmatched += 1
            logging.debug("Stop %s: could not resolve parish/municipality.", stop["stop_id"])

    if unmatched:
        logging.warning("%d stops (%.1f%%) could not be matched to a parish/municipality.",
                        unmatched, 100 * unmatched / len(stops))

    out_fieldnames = base_fieldnames if "stop_desc" in base_fieldnames else base_fieldnames + ["stop_desc"]
    with open(os.path.join(OUTPUT_GTFS_PATH, "stops.txt"), "w",
              encoding="utf-8", newline="") as out_fh:
        writer = csv.DictWriter(out_fh, fieldnames=out_fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(stops)

    logging.info("stops.txt written with stop_desc for %d stops.", len(stops))

    # Interurban lines may not pick up or drop off passengers within cities that
    # have their own urban network.  The rule is applied per trip:
    #   - If the FIRST stop is in a restricted municipality, all consecutive
    #     stops in that municipality (from the start) are marked pickup-only
    #     (dropoff_type=1) until the first stop outside it.
    #   - If the LAST stop is in a restricted municipality, all consecutive
    #     stops in that municipality (from the end) are marked dropoff-only
    #     (pickup_type=1) until the last stop outside it.
    #   - Stops in restricted municipalities that appear only in the middle of
    #     a trip are left with regular pickup/dropoff.
    RESTRICTED_MUNIS = {"15030", "27028", "32054", "15078", "36057"}

    # Build stop_id -> INE code dict from the already-loaded stops (O(1) lookups)
    stop_ine: dict[str, str] = {}
    for stop in stops:
        zone_id = stop.get("zone_id", "")
        stop_ine[stop["stop_id"]] = zone_id[:5] if len(zone_id) >= 5 else ""

    logging.info("Applying traffic restrictions for municipalities: %s …",
                 ", ".join(sorted(RESTRICTED_MUNIS)))

    with open(STOP_TIMES_FILE, encoding="utf-8-sig", newline="") as st_fh:
        st_reader = csv.DictReader(st_fh)
        all_stop_times = list(st_reader)
        st_fieldnames = list(st_reader.fieldnames or all_stop_times[0].keys())

    # Ensure pickup_type / dropoff_type columns exist (GTFS optional, default 0)
    for col in ("pickup_type", "dropoff_type"):
        if col not in st_fieldnames:
            st_fieldnames.append(col)
    for st in all_stop_times:
        st.setdefault("pickup_type", "0")
        st.setdefault("dropoff_type", "0")

    # Group by trip_id and sort each group by stop_sequence
    trips_stop_times: dict[str, list[dict]] = defaultdict(list)
    for st in all_stop_times:
        trips_stop_times[st["trip_id"]].append(st)
    for seq in trips_stop_times.values():
        seq.sort(key=lambda x: int(x["stop_sequence"]))

    restricted_trips = 0
    for seq in trips_stop_times.values():
        n = len(seq)

        # Prefix: how many consecutive stops from the START are in a restricted muni
        prefix_end = 0  # exclusive end index
        while prefix_end < n and stop_ine.get(seq[prefix_end]["stop_id"], "") in RESTRICTED_MUNIS:
            prefix_end += 1

        # Suffix: how many consecutive stops from the END are in a restricted muni
        suffix_start = n - 1  # will become inclusive start index after adjustment
        while suffix_start >= 0 and stop_ine.get(seq[suffix_start]["stop_id"], "") in RESTRICTED_MUNIS:
            suffix_start -= 1
        suffix_start += 1  # inclusive start of the suffix run

        first_is_restricted = prefix_end > 0
        last_is_restricted = suffix_start < n

        if not first_is_restricted and not last_is_restricted:
            continue

        # If prefix and suffix meet or overlap, the whole trip is within restricted
        # munis (likely a purely urban service not subject to these rules) — skip.
        if first_is_restricted and last_is_restricted and prefix_end >= suffix_start:
            continue

        if first_is_restricted:
            for st in seq[:prefix_end]:
                st["pickup_type"] = "0"  # regular pickup
                st["drop_off_type"] = "1"  # no dropoff

        if last_is_restricted:
            for st in seq[suffix_start:]:
                st["pickup_type"] = "1"  # no pickup
                st["drop_off_type"] = "0"  # regular dropoff

        restricted_trips += 1

    logging.info("Traffic restrictions applied to %d trips.", restricted_trips)

    with open(os.path.join(OUTPUT_GTFS_PATH, "stop_times.txt"), "w",
              encoding="utf-8", newline="") as st_out_fh:
        writer = csv.DictWriter(st_out_fh, fieldnames=st_fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_stop_times)

    # Package output ZIP
    with zipfile.ZipFile(OUTPUT_GTFS_ZIP, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(OUTPUT_GTFS_PATH):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, OUTPUT_GTFS_PATH)
                zipf.write(file_path, arcname)

    logging.info("GTFS feed zipped to %s", OUTPUT_GTFS_ZIP)

    # Cleanup
    os.close(INPUT_GTFS_FD)
    os.remove(INPUT_GTFS_ZIP)
    shutil.rmtree(INPUT_GTFS_PATH)
    shutil.rmtree(OUTPUT_GTFS_PATH)

