"""Descargador reanudable para la API V3 por id_dispositivo."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_API = "https://api-sensores.cmasccp.cl"


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def download(
    api_url: str,
    device_id: int,
    start_date: str,
    end_date: str,
    output_dir: Path,
    retries: int = 5,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"dispositivo-{device_id}_{start_date}_{end_date}"
    plain_part = output_dir / f"{stem}.ndjson.part"
    state_path = output_dir / f"{stem}.state.json"
    gzip_part = output_dir / f"{stem}.ndjson.gz.part"
    final_path = output_dir / f"{stem}.ndjson.gz"

    state: dict[str, Any] = {
        "cursor": None,
        "bytes": 0,
        "rows": 0,
        "complete": False,
    }
    if state_path.exists():
        state.update(json.loads(state_path.read_text(encoding="utf-8")))
    if plain_part.exists():
        with plain_part.open("r+b") as output:
            output.truncate(int(state["bytes"]))

    endpoint = (
        f"{api_url.rstrip('/')}/v3/dispositivos/{device_id}/historico.ndjson"
    )
    attempts = 0

    while not state["complete"]:
        confirmed_rows = int(state["rows"])
        params = {
            "fecha_inicio": start_date,
            "fecha_fin": end_date,
            "limite": 500,
        }
        if state["cursor"]:
            params["cursor"] = state["cursor"]

        try:
            with requests.get(
                endpoint,
                params=params,
                stream=True,
                timeout=(15, 180),
            ) as response:
                response.raise_for_status()
                with plain_part.open("ab") as output:
                    for line in response.iter_lines(decode_unicode=True):
                        if not line:
                            continue
                        item = json.loads(line)
                        if "_error" in item:
                            raise RuntimeError(item["_error"]["message"])
                        if "_meta" in item:
                            meta = item["_meta"]
                            state["cursor"] = meta.get("next_cursor")
                            state["rows"] = confirmed_rows + int(meta["rows"])
                            state["complete"] = bool(meta["complete"])
                            output.flush()
                            os.fsync(output.fileno())
                            state["bytes"] = output.tell()
                            atomic_json(state_path, state)
                            continue
                        output.write(
                            (
                            json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                            + "\n"
                            ).encode("utf-8")
                        )
            attempts = 0
        except (requests.RequestException, RuntimeError, json.JSONDecodeError) as error:
            if plain_part.exists():
                with plain_part.open("r+b") as output:
                    output.truncate(int(state["bytes"]))
            attempts += 1
            if attempts > retries:
                raise RuntimeError(
                    f"descarga fallida tras {retries} reintentos: {error}"
                ) from error
            delay = min(2**attempts, 30)
            print(f"Reintento {attempts}/{retries} en {delay}s: {error}", flush=True)
            time.sleep(delay)

    with plain_part.open("rb") as source, gzip.open(gzip_part, "wb") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)
    os.replace(gzip_part, final_path)
    plain_part.unlink()
    state_path.unlink()
    return final_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Descarga histórica V3 por id_dispositivo."
    )
    parser.add_argument("--device-id", type=int, required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("descargas"))
    parser.add_argument("--api-url", default=DEFAULT_API)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = download(
        args.api_url,
        args.device_id,
        args.start_date,
        args.end_date,
        args.output_dir,
    )
    print(f"Descarga completa: {path}", flush=True)


if __name__ == "__main__":
    main()
