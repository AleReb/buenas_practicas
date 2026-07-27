"""Blueprint V3 para consultar y descargar históricos por dispositivo.

Este módulo no reemplaza rutas legacy. Se registra con un prefijo /v3 y usa:

* filtros obligatorios por dispositivo y fecha;
* paginación keyset por (id_sensor, fecha, id_dato);
* lotes pequeños y acotados;
* streaming NDJSON con checkpoints reanudables.
"""

from __future__ import annotations

import base64
import json
from datetime import date, datetime
from typing import Any, Iterator

import decimal
import mysql.connector
from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    request,
    stream_with_context,
)


DEFAULT_PAGE_SIZE = 500
MAX_PAGE_SIZE = 1000


def _encode_cursor(id_sensor: int, fecha: datetime | str, id_dato: int) -> str:
    value = fecha.isoformat() if isinstance(fecha, datetime) else str(fecha)
    payload = json.dumps(
        [int(id_sensor), value, int(id_dato)],
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str | None) -> tuple[int, datetime, int] | None:
    if not value:
        return None
    try:
        padding = "=" * (-len(value) % 4)
        id_sensor, fecha, id_dato = json.loads(
            base64.urlsafe_b64decode(value + padding).decode()
        )
        return int(id_sensor), datetime.fromisoformat(fecha), int(id_dato)
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("cursor inválido") from error


def _parse_date(value: str | None, field: str) -> date:
    if not value:
        raise ValueError(f"{field} es obligatorio")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as error:
        raise ValueError(f"{field} debe usar YYYY-MM-DD") from error


def _serialize(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    return str(value)


def create_historico_v3_blueprint(db_config: dict[str, Any]) -> Blueprint:
    blueprint = Blueprint("historico_v3", __name__, url_prefix="/v3")

    def connect():
        connection = mysql.connector.connect(**db_config)
        connection.autocommit = True
        return connection

    def get_device(connection, device_id: int) -> tuple[dict[str, Any], list[int]]:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT id_dispositivo, codigo_interno, id_proyecto, descripcion
                FROM dispositivos
                WHERE id_dispositivo = %s
                """,
                (device_id,),
            )
            device = cursor.fetchone()
            if not device:
                raise LookupError("dispositivo no encontrado")

            cursor.execute(
                """
                SELECT id_sensor
                FROM sensores_en_dispositivo
                WHERE id_dispositivo = %s
                ORDER BY id_sensor
                """,
                (device_id,),
            )
            sensor_ids = [int(row["id_sensor"]) for row in cursor.fetchall()]
            if not sensor_ids:
                raise LookupError("el dispositivo no tiene sensores asociados")
            return device, sensor_ids
        finally:
            cursor.close()

    def fetch_page(
        connection,
        device: dict[str, Any],
        sensor_ids: list[int],
        start: date,
        end: date,
        cursor_value: tuple[int, datetime, int] | None,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        placeholders = ", ".join(["%s"] * len(sensor_ids))
        clauses = [
            f"d.id_sensor IN ({placeholders})",
            "d.fecha >= %s",
            "d.fecha < DATE_ADD(%s, INTERVAL 1 DAY)",
        ]
        params: list[Any] = [*sensor_ids, start, end]

        if cursor_value:
            cursor_sensor, cursor_date, cursor_id = cursor_value
            clauses.append(
                """
                (
                    d.id_sensor > %s
                    OR (
                        d.id_sensor = %s
                        AND (
                            d.fecha > %s
                            OR (d.fecha = %s AND d.id_dato > %s)
                        )
                    )
                )
                """
            )
            params.extend(
                [
                    cursor_sensor,
                    cursor_sensor,
                    cursor_date,
                    cursor_date,
                    cursor_id,
                ]
            )

        params.append(page_size)
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                f"""
                SELECT d.id_dato, d.fecha, d.fecha_insercion, d.id_sensor,
                       d.id_variable, d.id_sesion, d.valor,
                       v.descripcion AS variable_descripcion, v.unidad
                FROM datos AS d
                LEFT JOIN variables AS v
                  ON v.id_variable = d.id_variable
                WHERE {' AND '.join(clauses)}
                ORDER BY d.id_sensor ASC, d.fecha ASC, d.id_dato ASC
                LIMIT %s
                """,
                params,
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()

        for row in rows:
            row["id_dispositivo"] = device["id_dispositivo"]
            row["codigo_interno"] = device["codigo_interno"]
            row["id_proyecto"] = device["id_proyecto"]

        next_cursor = None
        if rows:
            last = rows[-1]
            next_cursor = _encode_cursor(
                last["id_sensor"],
                last["fecha"],
                last["id_dato"],
            )
        return rows, next_cursor

    def parse_request() -> tuple[
        date,
        date,
        int,
        tuple[int, datetime, int] | None,
    ]:
        start = _parse_date(request.args.get("fecha_inicio"), "fecha_inicio")
        end = _parse_date(request.args.get("fecha_fin"), "fecha_fin")
        if start > end:
            raise ValueError("fecha_inicio no puede ser posterior a fecha_fin")
        try:
            page_size = int(request.args.get("limite", DEFAULT_PAGE_SIZE))
        except ValueError as error:
            raise ValueError("limite debe ser entero") from error
        if page_size < 1:
            raise ValueError("limite debe ser mayor que cero")
        page_size = min(page_size, MAX_PAGE_SIZE)
        return start, end, page_size, _decode_cursor(request.args.get("cursor"))

    @blueprint.get("/dispositivos/<int:device_id>/mediciones")
    def list_measurements(device_id: int):
        try:
            start, end, page_size, cursor_value = parse_request()
        except ValueError as error:
            return jsonify({"status": "fail", "error": str(error)}), 400

        connection = None
        try:
            connection = connect()
            device, sensor_ids = get_device(connection, device_id)
            rows, next_cursor = fetch_page(
                connection,
                device,
                sensor_ids,
                start,
                end,
                cursor_value,
                page_size,
            )
            return jsonify(
                {
                    "status": "success",
                    "data": {
                        "dispositivo": device,
                        "mediciones": rows,
                        "next_cursor": next_cursor,
                        "has_more": len(rows) == page_size,
                    },
                }
            )
        except LookupError as error:
            return jsonify({"status": "fail", "error": str(error)}), 404
        except mysql.connector.Error:
            current_app.logger.exception("Error de MariaDB en mediciones V3")
            return jsonify(
                {"status": "fail", "error": "error consultando la base de datos"}
            ), 503
        finally:
            if connection is not None and connection.is_connected():
                connection.close()

    @blueprint.get("/dispositivos/<int:device_id>/historico.ndjson")
    def stream_history(device_id: int):
        try:
            start, end, page_size, cursor_value = parse_request()
        except ValueError as error:
            return jsonify({"status": "fail", "error": str(error)}), 400

        @stream_with_context
        def generate() -> Iterator[str]:
            connection = None
            emitted = 0
            current_cursor = cursor_value
            try:
                connection = connect()
                device, sensor_ids = get_device(connection, device_id)
                while True:
                    rows, next_cursor = fetch_page(
                        connection,
                        device,
                        sensor_ids,
                        start,
                        end,
                        current_cursor,
                        page_size,
                    )
                    for row in rows:
                        yield json.dumps(
                            row,
                            default=_serialize,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ) + "\n"
                    emitted += len(rows)
                    if not rows or len(rows) < page_size:
                        yield json.dumps(
                            {
                                "_meta": {
                                    "complete": True,
                                    "rows": emitted,
                                    "next_cursor": None,
                                }
                            },
                            separators=(",", ":"),
                        ) + "\n"
                        break
                    current_cursor = _decode_cursor(next_cursor)
                    yield json.dumps(
                        {
                            "_meta": {
                                "complete": False,
                                "rows": emitted,
                                "next_cursor": next_cursor,
                            }
                        },
                        separators=(",", ":"),
                    ) + "\n"
            except LookupError as error:
                yield json.dumps(
                    {"_error": {"status": 404, "message": str(error)}},
                    separators=(",", ":"),
                ) + "\n"
            except mysql.connector.Error:
                current_app.logger.exception("Error de MariaDB en histórico V3")
                yield json.dumps(
                    {
                        "_error": {
                            "status": 503,
                            "message": "error consultando la base de datos",
                        }
                    },
                    separators=(",", ":"),
                ) + "\n"
            finally:
                if connection is not None and connection.is_connected():
                    connection.close()

        return Response(
            generate(),
            mimetype="application/x-ndjson",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
                "Content-Disposition": (
                    f'attachment; filename="dispositivo-{device_id}-historico.ndjson"'
                ),
            },
        )

    return blueprint


__all__ = [
    "create_historico_v3_blueprint",
    "_decode_cursor",
    "_encode_cursor",
    "_parse_date",
]
