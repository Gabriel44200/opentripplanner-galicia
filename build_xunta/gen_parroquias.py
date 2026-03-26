# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "osmium",
#     "shapely",
#     "requests",
#     "tqdm",
# ]
# ///

import json
import logging
import sys
from argparse import ArgumentParser
from pathlib import Path

import osmium
import osmium.geom
import requests
from shapely.wkb import loads as wkb_loads
from tqdm import tqdm

GEOFABRIK_URL = "https://download.geofabrik.de/europe/spain/galicia-latest.osm.pbf"
DEFAULT_PBF = "galicia-latest.osm.pbf"
DEFAULT_OUTPUT = "parroquias.geojson"

_wkb_factory = osmium.geom.WKBFactory()


class _AdminBoundaryHandler(osmium.SimpleHandler):
    """Collects administrative boundary areas at the requested admin levels."""

    def __init__(self, admin_levels: set[str]) -> None:
        super().__init__()
        self.admin_levels = admin_levels
        self.features: list[dict] = []
        self._geom_errors = 0

    def area(self, a: osmium.osm.Area) -> None:  # type: ignore[name-defined]
        tags = a.tags
        if tags.get("boundary") != "administrative":
            return
        level = tags.get("admin_level")
        if level not in self.admin_levels:
            return

        try:
            wkb = _wkb_factory.create_multipolygon(a)
            geom = wkb_loads(wkb, hex=True)
        except Exception:
            self._geom_errors += 1
            return

        ref_ine = tags.get("ref:ine", "")
        self.features.append(
            {
                "type": "Feature",
                "geometry": geom.__geo_interface__,
                "properties": {
                    "osm_type": "way" if a.from_way() else "relation",
                    "osm_id": a.orig_id(),
                    "admin_level": int(level),
                    "name": tags.get("name", ""),
                    "name_gl": tags.get("name:gl", ""),
                    # ref:ine full code (e.g. "15017000000" for a municipality,
                    # "15017030000" for a parish).  First 5 chars are always the
                    # 5-digit INE municipality code (PP+MMM).
                    "ref_ine": ref_ine,
                    "ine_muni": tags.get("ine:municipio", ref_ine[:5] if ref_ine else ""),
                    "wikidata": tags.get("wikidata", ""),
                },
            }
        )


def _download_pbf(url: str, dest: Path) -> None:
    """Stream-download *url* to *dest*, showing a progress bar.

    Skips the download silently if *dest* already exists.
    """
    if dest.exists():
        logging.info("PBF already present at %s — skipping download.", dest)
        return

    logging.info("Downloading %s …", url)
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        with open(dest, "wb") as fh, tqdm(
            total=total, unit="B", unit_scale=True, desc=dest.name
        ) as bar:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
                bar.update(len(chunk))

    logging.info("Download complete: %s (%.1f MB)", dest, dest.stat().st_size / 1e6)


def main() -> None:
    parser = ArgumentParser(
        description=(
            "Extract Galician parish (admin_level=9) and municipality "
            "(admin_level=8) boundaries from an OSM PBF file."
        )
    )
    parser.add_argument(
        "--pbf",
        type=Path,
        default=Path(DEFAULT_PBF),
        help=f"Path to OSM PBF file.  Downloaded from Geofabrik if absent "
             f"(default: {DEFAULT_PBF}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT),
        help=f"Output GeoJSON file (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Do not attempt to download the PBF; fail if it is missing.",
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

    if not args.no_download:
        _download_pbf(GEOFABRIK_URL, args.pbf)

    if not args.pbf.exists():
        logging.error("PBF file not found: %s", args.pbf)
        sys.exit(1)

    logging.info("Parsing admin boundaries from %s …", args.pbf)
    handler = _AdminBoundaryHandler(admin_levels={"8", "9"})
    handler.apply_file(str(args.pbf), locations=True, idx="flex_mem")

    n = len(handler.features)
    logging.info(
        "Found %d boundary features (%d geometry errors skipped).",
        n,
        handler._geom_errors,
    )
    if n == 0:
        logging.warning(
            "No boundaries found — check that the PBF covers Galicia and "
            "contains boundary=administrative relations at admin_level 8/9."
        )

    geojson = {
        "type": "FeatureCollection",
        "features": handler.features,
    }

    args.output.write_text(
        json.dumps(geojson, ensure_ascii=False, indent=None),
        encoding="utf-8",
    )
    logging.info("Saved %d features to %s", n, args.output)


if __name__ == "__main__":
    main()
