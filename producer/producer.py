from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List
from dateutil import parser as dtparser
from datetime import datetime
import paho.mqtt.client as mqtt
import threading

from openf1_client import OpenF1Query, fetch_cached

CACHE_DIR = "/app/cache"

@dataclass(frozen=True)
class Config:
    mqtt_host: str
    mqtt_port: int
    base_topic: str
    session_key: int
    driver_numbers: List[int]
    replay_speedup: float

def env_config() -> Config:
    mqtt_host = os.getenv("MQTT_HOST", "localhost")
    mqtt_port = int(os.getenv("MQTT_PORT", "1883"))
    base_topic = os.getenv("MQTT_BASE_TOPIC", "f1/monza").rstrip("/")
    session_key = int(os.getenv("SESSION_KEY", "0"))
    driver_numbers = [int(x.strip()) for x in os.getenv("DRIVER_NUMBERS", "16").split(",") if x.strip()]
    replay_speedup = float(os.getenv("REPLAY_SPEEDUP", "1.0"))
    if replay_speedup <= 0:
        replay_speedup = 1.0
    return Config(mqtt_host, mqtt_port, base_topic, session_key, driver_numbers, replay_speedup)

def parse_ts(s: str) -> float:
    return dtparser.isoparse(s).timestamp()

def to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except Exception:
        return None

def to_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except Exception:
        return None

def normalize_car_data(row: Dict[str, Any]) -> Dict[str, Any]:
    ts = row.get("date") or row.get("ts") or row.get("timestamp")
    out = {
        "ts": ts,
        "speed": to_float(row.get("speed")),
        "throttle": to_float(row.get("throttle")),
        "brake": to_int(row.get("brake")),
        "rpm": to_int(row.get("rpm")),
        "gear": to_int(row.get("n_gear") or row.get("gear")),
        "drs": to_int(row.get("drs")),
        "driver": to_int(row.get("driver_number") or row.get("driver")),
    }
    return {k: v for k, v in out.items() if v is not None}

def normalize_location(row: Dict[str, Any]) -> Dict[str, Any]:
    ts = row.get("date") or row.get("ts") or row.get("timestamp")
    out = {
        "ts": ts,
        "x": to_float(row.get("x")),
        "y": to_float(row.get("y")),
        "z": to_float(row.get("z")),
        "driver": to_int(row.get("driver_number") or row.get("driver")),
    }
    return {k: v for k, v in out.items() if v is not None}

def publish_stream(
    client: mqtt.Client,
    topic_prefix: str,
    measurement: str,
    rows: List[Dict[str, Any]],
    speedup: float,
    driver_num: int
) -> None:
    rows = [r for r in rows if r.get("ts")]
    rows.sort(key=lambda r: parse_ts(r["ts"]))

    if not rows:
        print(f"[WARN] no rows for {measurement}")
        return

    t0 = parse_ts(rows[0]["ts"])
    t_last = parse_ts(rows[-1]["ts"])
    sim_duration = (t_last - t0) / speedup
    print(f"[INFO] {measurement}: rows={len(rows)} sim_duration={sim_duration:.1f}s (speedup={speedup})")

    wall0 = time.time()
    last_report = wall0

    for i, r in enumerate(rows, start=1):
        ts = parse_ts(r["ts"])
        sim_dt = (ts - t0) / speedup
        target_wall = wall0 + sim_dt
        sleep_s = target_wall - time.time()
        if sleep_s > 0:
            time.sleep(sleep_s)

        topic = f"{topic_prefix}/{measurement}"
        payload = r

        client.publish(topic, json.dumps(payload), qos=0, retain=False)

        now = time.time()
        if now - last_report >= 5.0:
            print(f"[INFO] publishing (car {driver_num}) {measurement}: {i}/{len(rows)}")
            last_report = now


def run_driver_streams(client, topic_prefix, driver_num: int, car_rows, loc_rows, speedup: float):
    print(f"[INFO] replay driver={driver_num} car_rows={len(car_rows)} loc_rows={len(loc_rows)} speedup={speedup}")

    t_telemetry = threading.Thread(
        target=publish_stream,
        args=(client, topic_prefix, "telemetry", car_rows, speedup, driver_num),
        daemon=True
    )

    t_location = threading.Thread(
        target=publish_stream,
        args=(client, topic_prefix, "location", loc_rows, speedup, driver_num),
        daemon=True
    )

    t_telemetry.start()
    t_location.start()
    t_telemetry.join()
    t_location.join()


def trim_from_race_start(car_rows, speed_threshold=60, min_continuous_seconds=120, max_gap_seconds=3):
    start_idx = None
    t_start = None
    t_prev = None

    for i, row in enumerate(car_rows):
        speed = row.get("speed", 0) or 0
        ts = parse_iso(row["ts"])

        if speed >= speed_threshold:
            if t_start is None:
                start_idx = i
                t_start = ts
                t_prev = ts
            else:
                if (ts - t_prev).total_seconds() > max_gap_seconds:
                    start_idx = i
                    t_start = ts
                t_prev = ts
            if (ts - t_start).total_seconds() >= min_continuous_seconds:
                print(f"[INFO] Race start detected at {t_start}")
                return car_rows[start_idx:]
        else:
            t_start = None
            start_idx = None
            t_prev = None
    
    print("[WARN] Race start not detected, no trimming applied.")
    return car_rows


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))



def main() -> None:
    cfg = env_config()

    if cfg.session_key == 0:
        print("[ERROR] SESSION_KEY=0. Devi impostare session_key della sessione desiderata.")
        return

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(cfg.mqtt_host, cfg.mqtt_port, keepalive=60)
    client.loop_start()

    driver_threads = []

    for driver in cfg.driver_numbers:
        car_rows_raw = fetch_cached(
            OpenF1Query(
                endpoint="car_data",
                params={"session_key": cfg.session_key, "driver_number": driver},
                fmt="json",
            ),
            cache_dir=CACHE_DIR,
        )

        loc_rows_raw = fetch_cached(
            OpenF1Query(
                endpoint="location",
                params={"session_key": cfg.session_key, "driver_number": driver},
                fmt="json",
            ),
            cache_dir=CACHE_DIR,
        )

        car_rows = [normalize_car_data(r) for r in car_rows_raw]
        loc_rows = [normalize_location(r) for r in loc_rows_raw]

        car_rows = trim_from_race_start(car_rows)
        loc_rows = loc_rows[-len(car_rows):]

        driver_topic_prefix = f"{cfg.base_topic}/unknown/sk{cfg.session_key}/{driver}"

        t = threading.Thread(
            target=run_driver_streams,
            args=(client, driver_topic_prefix, driver, car_rows, loc_rows, cfg.replay_speedup),
            daemon=True
        )

        t.start()
        driver_threads.append(t)

    for t in driver_threads:
        t.join()

    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()