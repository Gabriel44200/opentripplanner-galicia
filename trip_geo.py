# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pandas",
# ]
# ///

import argparse
import os
import pandas as pd

if __name__ != "__main__":
    raise RuntimeError("This script is meant to be run as a standalone program, not imported as a module.")

parser = argparse.ArgumentParser(description="Extract GeoJSON from GTFS feed and save to file")
parser.add_argument(
    "gtfs_path",
    type=str,
    help="Path to the GTFS feed directory"
)

parser.add_argument(
    "trip_id",
    type=str,
    help="ID of the trip to extract from the GTFS feed"
)

args = parser.parse_args()

gtfs_path = args.gtfs_path
trip_id = args.trip_id

# Load trips.txt, stop_times.txt, stops.txt and shapes.txt

trips_df = pd.read_csv(os.path.join(gtfs_path, "trips.txt"))
stop_times_df = pd.read_csv(os.path.join(gtfs_path, "stop_times.txt"))
stops_df = pd.read_csv(os.path.join(gtfs_path, "stops.txt"))
shapes_df = pd.read_csv(os.path.join(gtfs_path, "shapes.txt"))

# Find the shape_id for the given trip_id
trip_row = trips_df[trips_df["trip_id"] == trip_id]
if trip_row.empty:
    raise ValueError(f"Trip ID {trip_id} not found in trips.txt")

shape_id = trip_row.iloc[0]["shape_id"]
if pd.isna(shape_id):
    raise ValueError(f"No shape_id found for Trip ID {trip_id}")

# Extract the shape points for the shape_id
shape_points = shapes_df[shapes_df["shape_id"] == shape_id].sort_values(by="shape_pt_sequence")

# Find the stop sequence for the trip_id and get the stop coordinates
stop_times = stop_times_df[stop_times_df["trip_id"] == trip_id].sort_values(by="stop_sequence")
stop_ids = stop_times["stop_id"].tolist()
stops = stops_df[stops_df["stop_id"].isin(stop_ids)]

# Convert shape points to GeoJSON LineString format
geojson = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": shape_points.apply(lambda row: [row["shape_pt_lon"], row["shape_pt_lat"]], axis=1).tolist()
            },
            "properties": {
                "headsign": trip_row.iloc[0]["trip_headsign"],
                "shape_id": shape_id
            }
        },
        *[{
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [x.stop_lon, x.stop_lat]
            },
            "properties": {
                "name": x.stop_name,
                "stop_id": x.stop_id,
                "code": x.stop_code
            }
        } for _, x in stops.iterrows()]
    ]
}

# Save GeoJSON to file
output_file = f"{trip_id}_shape.geojson"

with open(output_file, "w") as f:
    import json
    json.dump(geojson, f, indent=2)
