# Use a multi-stage build to download necessary files
FROM alpine/curl AS downloader

RUN curl -L https://download.geofabrik.de/europe/spain-latest.osm.pbf -o /spain-latest.osm.pbf

FROM osrm/osrm-backend AS builder

# Copy the downloaded OSM file from the downloader stage
RUN mkdir -p /data/standard /data/narrow
COPY --from=downloader /spain-latest.osm.pbf /data/standard/spain-latest.osm.pbf
COPY --from=downloader /spain-latest.osm.pbf /data/narrow/spain-latest.osm.pbf
COPY ./train_standard.lua /opt/train_standard.lua
COPY ./train_narrow.lua /opt/train_narrow.lua

# Extract the map data using osrm-train-profile (by Railnova)
RUN osrm-extract -p /opt/train_standard.lua /data/standard/spain-latest.osm.pbf
RUN osrm-partition /data/standard/spain-latest.osrm

# Prepare the map data for routing
RUN osrm-extract -p /opt/train_narrow.lua /data/narrow/spain-latest.osm.pbf
RUN osrm-partition /data/narrow/spain-latest.osrm

RUN osrm-customize /data/standard/spain-latest.osrm
RUN osrm-customize /data/narrow/spain-latest.osrm

RUN rm /data/standard/spain-latest.osm.pbf
RUN rm /data/narrow/spain-latest.osm.pbf

FROM osrm/osrm-backend

RUN mkdir -p /data/standard /data/narrow
COPY --from=builder /data/standard/spain-latest.osrm* /data/standard/
COPY --from=builder /data/narrow/spain-latest.osrm* /data/narrow/

# Expose the OSRM server port
EXPOSE 5000 5001

# Start the OSRM server
COPY ./start.sh /start.sh
RUN chmod +x /start.sh
EXPOSE 5000 5001
CMD ["/start.sh"]