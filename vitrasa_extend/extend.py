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

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    GTFS_TEMPWORKDIR = tempfile.mkdtemp(prefix="vitrasa_extend_")

    # Unzip the GTFS feed
    with zipfile.ZipFile("../feeds/vitrasa.zip", "r") as zip_ref:
        zip_ref.extractall(GTFS_TEMPWORKDIR)

    CALENDAR_DATES_FILE = os.path.join(GTFS_TEMPWORKDIR, "calendar_dates.txt")
    # Open the calendar_dates.txt file, and copy 

    # Create a ZIP archive of the output GTFS
    with zipfile.ZipFile("../feeds/vitrasa_fixed.zip", "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(GTFS_TEMPWORKDIR):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, GTFS_TEMPWORKDIR)
                zipf.write(file_path, arcname)

    logging.info(
        "GTFS data from feed has been zipped successfully at ../feeds/vitrasa_fixed.zip."
    )

    shutil.rmtree(GTFS_TEMPWORKDIR)
