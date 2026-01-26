# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "requests",
# ]
# ///


import json
import requests
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


class Config:
    gtfs_url: str = ""
    ntfy_topic: str = ""
    lastfeed: str = ""
    file_to_monitor: str = ""

    def __init__(
        self, gtfs_url: str, ntfy_topic: str, lastfeed: str, file_to_monitor: str
    ) -> None:
        self.gtfs_url = gtfs_url
        self.ntfy_topic = ntfy_topic
        self.lastfeed = lastfeed
        self.file_to_monitor = file_to_monitor


def load_config(config_path: str) -> Config:
    """Load the lastfeed data from a local source."""
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

        return Config(
            data["gtfs_url"],
            data["ntfy_topic"],
            data["lastfeed"],
            data.get("file_to_monitor", ""),
        )


def save_config(config_path: str, config: Config) -> None:
    """Save the lastfeed data to a local source."""
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "gtfs_url": config.gtfs_url,
                "ntfy_topic": config.ntfy_topic,
                "lastfeed": config.lastfeed,
                "file_to_monitor": config.file_to_monitor,
            },
            f,
            ensure_ascii=False,
            indent=4,
        )


def load_gtfs_last_modified(url: str) -> datetime | None:
    """Perform a HEAD request to the GTFS service to get last modification date."""
    response = requests.head(url, timeout=10)
    response.raise_for_status()
    last_modified = response.headers.get("Last-Modified")
    if last_modified:
        return parsedate_to_datetime(last_modified)
    return None


def format_date_spanish(dt: datetime) -> str:
    """Format a datetime object into a Spanish date string."""
    months = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]
    day = dt.day
    month = months[dt.month - 1]
    time = dt.strftime("%H:%M")
    return f"{day} de {month}, {time}"


def push_ntfy(topic: str, message: str, title: str, priority: str = "default", tags: str = "") -> None:
    """Push notification using ntfy service."""
    requests.post(
        f"https://ntfy.sh/{topic}",
        data=message.encode("utf-8"),
        headers={
            "Priority": priority,
            "Tags": tags,
            "Title": title
        },
        timeout=10
    )


if __name__ == "__main__":
    # Get the directory where the script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.json")

    conf = load_config(config_path)

    current_last_modified = load_gtfs_last_modified(conf.gtfs_url)
    if not current_last_modified:
        print("Could not get last modification date.")
    else:
        # datetime.fromisoformat supports 'Z' in Python 3.11+
        stored_last_modified = datetime.fromisoformat(conf.lastfeed)

        # 1. Check if server has a NEWER feed than what we LAST NOTIFIED about
        if current_last_modified > stored_last_modified:
            formatted_date = format_date_spanish(current_last_modified)
            print(f"New GTFS found: {formatted_date}")
            msg = f"Nuevo GTFS de Vitrasa con fecha {formatted_date}"
            push_ntfy(conf.ntfy_topic, msg, "Nuevo GTFS listo", priority="high", tags="rotating_light")

            # Update config with new date
            conf.lastfeed = current_last_modified.isoformat().replace("+00:00", "Z")
            save_config(config_path, conf)
        else:
            print("GTFS server date has not changed since last notification.")

        # 2. Check if the LOCAL file is currently outdated compared to the server
        if conf.file_to_monitor:
            # Resolve relative path from script location if necessary
            full_path = os.path.normpath(os.path.join(script_dir, conf.file_to_monitor))
            if os.path.exists(full_path):
                file_mtime = datetime.fromtimestamp(os.path.getmtime(full_path), tz=timezone.utc)
                if file_mtime < current_last_modified:
                    formatted_file_mtime = format_date_spanish(file_mtime)
                    formatted_feed_mtime = format_date_spanish(current_last_modified)

                    print(f"Warning: Local file {conf.file_to_monitor} is outdated.")
                    msg = (
                        f"El archivo local ({formatted_file_mtime}) "
                        f"es anterior al feed disponible ({formatted_feed_mtime})"
                    )
                    push_ntfy(conf.ntfy_topic, msg, "Archivo GTFS desactualizado", priority="default", tags="warning")
                else:
                    print(f"Local file {conf.file_to_monitor} is up to date.")
            else:
                print(f"File to monitor not found: {full_path}")
