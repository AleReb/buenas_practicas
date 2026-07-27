"""Conversor por streaming de NDJSON o NDJSON.GZ a CSV."""

from __future__ import annotations

import argparse
import csv
import glob
import gzip
import json
import os
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TextIO


PREFERRED_COLUMNS = (
    "id_dispositivo",
    "codigo_interno",
    "id_proyecto",
    "id_sensor",
    "id_variable",
    "variable_descripcion",
    "unidad",
    "fecha",
    "fecha_insercion",
    "valor",
    "id_dato",
    "id_sesion",
)


def _open_text(path: Path) -> TextIO:
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def _records(path: Path) -> Iterator[dict[str, Any]]:
    with _open_text(path) as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"{path}: JSON inválido en la línea {line_number}"
                ) from error
            if not isinstance(item, dict):
                raise ValueError(
                    f"{path}: la línea {line_number} no contiene un objeto JSON"
                )
            if "_error" in item:
                message = item["_error"].get("message", "error sin detalle")
                raise RuntimeError(f"{path}: {message}")
            if "_meta" in item:
                continue
            yield item


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return value


def _replace_with_retry(source: Path, destination: Path) -> None:
    for attempt in range(8):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(min(0.05 * (2**attempt), 1))


def default_csv_path(source: Path, layout: str = "long") -> Path:
    without_gzip = source.with_suffix("") if source.suffix.lower() == ".gz" else source
    csv_path = without_gzip.with_suffix(".csv")
    if layout == "wide":
        return csv_path.with_name(csv_path.stem + ".wide.csv")
    return csv_path


def expand_inputs(inputs: list[Path]) -> list[Path]:
    """Expande comodines también en shells que no lo hacen, como PowerShell."""
    expanded: list[Path] = []
    for source in inputs:
        value = str(source)
        if any(character in value for character in "*?[]"):
            matches = [Path(match) for match in sorted(glob.glob(value))]
            expanded.extend(matches or [source])
        else:
            expanded.append(source)
    return expanded


def _integer_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ordered_columns(discovered: list[str]) -> list[str]:
    available = set(discovered)
    preferred = [name for name in PREFERRED_COLUMNS if name in available]
    return preferred + [name for name in discovered if name not in PREFERRED_COLUMNS]


def _series_key(record: dict[str, Any]) -> tuple[str, str]:
    return str(record.get("id_sensor") or ""), str(record.get("id_variable") or "")


def _series_sort_key(item: tuple[str, str]) -> tuple[Any, ...]:
    sensor, variable = item
    sensor_number = _integer_or_none(sensor)
    variable_number = _integer_or_none(variable)
    return (
        sensor_number is None,
        sensor_number if sensor_number is not None else 0,
        sensor,
        variable_number is None,
        variable_number if variable_number is not None else 0,
        variable,
    )


def _series_header(record: dict[str, Any]) -> str:
    sensor, variable = _series_key(record)
    description = str(record.get("variable_descripcion") or "sin_descripcion")
    unit = record.get("unidad")
    header = f"sensor_{sensor}__variable_{variable}__{description}"
    if unit not in (None, ""):
        header += f" [{unit}]"
    return header


def _order_clause(sort_by: str) -> str:
    numeric_sensor = (
        "sensor_number IS NULL, sensor_number, sensor_text"
    )
    numeric_data = "data_number IS NULL, data_number, data_text"
    if sort_by == "fecha":
        return f"fecha, {numeric_sensor}, {numeric_data}, sequence"
    if sort_by == "sensor":
        return f"{numeric_sensor}, fecha, {numeric_data}, sequence"
    if sort_by == "original":
        return "sequence"
    raise ValueError("sort_by debe ser 'fecha', 'sensor' u 'original'")


def convert_file(
    source: Path,
    destination: Path | None = None,
    delimiter: str = ";",
    sort_by: str = "fecha",
    layout: str = "long",
) -> tuple[Path, int]:
    """Convierte y ordena usando almacenamiento temporal, no memoria masiva."""
    source = Path(source)
    destination = (
        Path(destination)
        if destination
        else default_csv_path(source, layout=layout)
    )
    if not source.is_file():
        raise FileNotFoundError(f"no existe el archivo de entrada: {source}")
    if len(delimiter) != 1:
        raise ValueError("el delimitador CSV debe ser un solo carácter")
    if layout not in {"long", "wide"}:
        raise ValueError("layout debe ser 'long' o 'wide'")
    if layout == "wide" and sort_by != "fecha":
        raise ValueError("el formato wide requiere orden cronológico por fecha")
    if source.resolve() == destination.resolve():
        raise ValueError("la entrada y la salida no pueden ser el mismo archivo")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    sort_database = destination.with_suffix(
        destination.suffix + ".sort.sqlite.part"
    )
    sort_database.unlink(missing_ok=True)
    connection = sqlite3.connect(sort_database)
    try:
        connection.execute("PRAGMA journal_mode = OFF")
        connection.execute("PRAGMA synchronous = OFF")
        connection.execute(
            """
            CREATE TABLE records (
                sequence INTEGER PRIMARY KEY,
                fecha TEXT NOT NULL,
                sensor_number INTEGER,
                sensor_text TEXT NOT NULL,
                data_number INTEGER,
                data_text TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )

        discovered_columns: list[str] = []
        known_columns: set[str] = set()
        series: dict[tuple[str, str], dict[str, Any]] = {}
        row_count = 0
        for record in _records(source):
            row_count += 1
            for name in record:
                if name not in known_columns:
                    known_columns.add(name)
                    discovered_columns.append(name)
            series.setdefault(_series_key(record), record)
            sensor = record.get("id_sensor")
            data_id = record.get("id_dato")
            connection.execute(
                """
                INSERT INTO records (
                    sequence, fecha, sensor_number, sensor_text,
                    data_number, data_text, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_count,
                    str(record.get("fecha") or ""),
                    _integer_or_none(sensor),
                    str(sensor or ""),
                    _integer_or_none(data_id),
                    str(data_id or ""),
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
            )
        connection.commit()

        if layout == "wide":
            series_headers = {
                key: _series_header(series[key])
                for key in sorted(series, key=_series_sort_key)
            }
            columns = [
                "id_dispositivo",
                "codigo_interno",
                "id_proyecto",
                "fecha",
                *series_headers.values(),
            ]
        else:
            series_headers = {}
            columns = _ordered_columns(discovered_columns)
        with temporary.open("w", newline="", encoding="utf-8-sig") as target:
            if columns:
                writer = csv.DictWriter(
                    target,
                    fieldnames=columns,
                    delimiter=delimiter,
                    extrasaction="ignore",
                )
                writer.writeheader()
                query = (
                    "SELECT payload FROM records ORDER BY "
                    + _order_clause(sort_by)
                )
                if layout == "wide":
                    current_key: tuple[Any, Any] | None = None
                    wide_row: dict[str, Any] = {}
                    for (payload,) in connection.execute(query):
                        record = json.loads(payload)
                        key = (
                            record.get("id_dispositivo"),
                            record.get("fecha"),
                        )
                        if current_key is not None and key != current_key:
                            writer.writerow(wide_row)
                            wide_row = {}
                        if key != current_key:
                            current_key = key
                            wide_row = {
                                "id_dispositivo": record.get("id_dispositivo"),
                                "codigo_interno": record.get("codigo_interno"),
                                "id_proyecto": record.get("id_proyecto"),
                                "fecha": record.get("fecha"),
                            }
                        wide_row[series_headers[_series_key(record)]] = _csv_value(
                            record.get("valor")
                        )
                    if current_key is not None:
                        writer.writerow(wide_row)
                else:
                    for (payload,) in connection.execute(query):
                        record = json.loads(payload)
                        writer.writerow(
                            {
                                name: _csv_value(value)
                                for name, value in record.items()
                            }
                        )
            target.flush()
            os.fsync(target.fileno())
    finally:
        connection.close()
        sort_database.unlink(missing_ok=True)

    _replace_with_retry(temporary, destination)
    return destination, row_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convierte uno o más archivos NDJSON o NDJSON.GZ a CSV."
    )
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Carpeta de salida; por defecto usa la carpeta de cada entrada.",
    )
    parser.add_argument(
        "--delimiter",
        default=";",
        help="Separador CSV de un carácter; por defecto ';' para Excel en español.",
    )
    parser.add_argument(
        "--sort-by",
        choices=("fecha", "sensor", "original"),
        default="fecha",
        help="Orden de las filas; por defecto cronológico por fecha.",
    )
    parser.add_argument(
        "--layout",
        choices=("long", "wide"),
        default="long",
        help="Formato largo o variables como columnas; por defecto long.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for source in expand_inputs(args.inputs):
        destination = None
        if args.output_dir:
            destination = (
                args.output_dir
                / default_csv_path(source, layout=args.layout).name
            )
        csv_path, rows = convert_file(
            source,
            destination=destination,
            delimiter=args.delimiter,
            sort_by=args.sort_by,
            layout=args.layout,
        )
        print(
            f"CSV completo: {csv_path} ({rows} mediciones procesadas)",
            flush=True,
        )


if __name__ == "__main__":
    main()
