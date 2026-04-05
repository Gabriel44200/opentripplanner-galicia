#!/bin/sh
osrm-routed --algorithm mld --port 5000 /data/standard/spain-latest.osrm &
osrm-routed --algorithm mld --port 5001 /data/narrow/spain-latest.osrm