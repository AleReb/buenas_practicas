import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from ndjson_to_csv import convert_file, default_csv_path, expand_inputs


class CsvConversionTests(unittest.TestCase):
    def test_converts_gzip_and_ignores_stream_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "history.ndjson.gz"
            items = [
                {
                    "id_dispositivo": 224,
                    "id_sensor": 1028,
                    "id_dato": 2,
                    "fecha": "2026-04-22T12:30:00",
                    "valor": 1.5,
                    "detalle": {"calidad": "válida"},
                },
                {
                    "id_dispositivo": 224,
                    "id_sensor": 1029,
                    "id_dato": 1,
                    "fecha": "2026-04-22T12:20:00",
                    "valor": 2.5,
                    "unidad": "ppm",
                },
                {"_meta": {"complete": True, "rows": 2}},
            ]
            with gzip.open(source, "wt", encoding="utf-8") as target:
                for item in items:
                    target.write(json.dumps(item, ensure_ascii=False) + "\n")

            destination, rows = convert_file(source)

            self.assertEqual(destination, Path(directory) / "history.csv")
            self.assertEqual(rows, 2)
            with destination.open(
                "r",
                newline="",
                encoding="utf-8-sig",
            ) as converted:
                result = list(csv.DictReader(converted, delimiter=";"))
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["id_sensor"], "1029")
            self.assertEqual(result[0]["unidad"], "ppm")
            self.assertEqual(result[1]["detalle"], '{"calidad":"válida"}')
            self.assertEqual(
                list(result[0]),
                [
                    "id_dispositivo",
                    "id_sensor",
                    "unidad",
                    "fecha",
                    "valor",
                    "id_dato",
                    "detalle",
                ],
            )
            self.assertFalse(destination.with_suffix(".csv.part").exists())
            self.assertFalse(
                destination.with_suffix(".csv.sort.sqlite.part").exists()
            )

    def test_can_preserve_sensor_first_order(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "history.ndjson"
            records = [
                {
                    "id_sensor": 20,
                    "fecha": "2026-01-01T10:00:00",
                    "id_dato": 2,
                },
                {
                    "id_sensor": 10,
                    "fecha": "2026-01-01T11:00:00",
                    "id_dato": 1,
                },
            ]
            source.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )

            destination, _ = convert_file(source, sort_by="sensor")

            with destination.open(
                "r",
                newline="",
                encoding="utf-8-sig",
            ) as converted:
                result = list(csv.DictReader(converted, delimiter=";"))
            self.assertEqual(
                [row["id_sensor"] for row in result],
                ["10", "20"],
            )

    def test_wide_layout_places_series_in_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "history.ndjson"
            records = [
                {
                    "id_dispositivo": 225,
                    "codigo_interno": "HIRIPRO-V2",
                    "id_proyecto": 18,
                    "id_sensor": 1039,
                    "id_variable": 3,
                    "variable_descripcion": "Grados celcius",
                    "unidad": "°C",
                    "fecha": "2026-04-22T15:34:24",
                    "valor": 20.5,
                    "id_dato": 2,
                },
                {
                    "id_dispositivo": 225,
                    "codigo_interno": "HIRIPRO-V2",
                    "id_proyecto": 18,
                    "id_sensor": 1039,
                    "id_variable": 3,
                    "variable_descripcion": "Grados celcius",
                    "unidad": "°C",
                    "fecha": "2026-04-22T15:38:54",
                    "valor": 20.8,
                    "id_dato": 3,
                },
                {
                    "id_dispositivo": 225,
                    "codigo_interno": "HIRIPRO-V2",
                    "id_proyecto": 18,
                    "id_sensor": 1041,
                    "id_variable": 3,
                    "variable_descripcion": "Grados celcius",
                    "unidad": "°C",
                    "fecha": "2026-04-22T15:34:24",
                    "valor": 21.801,
                    "id_dato": 1,
                },
            ]
            source.write_text(
                "".join(
                    json.dumps(record, ensure_ascii=False) + "\n"
                    for record in records
                ),
                encoding="utf-8",
            )

            destination, measurements = convert_file(source, layout="wide")

            with destination.open(
                "r",
                newline="",
                encoding="utf-8-sig",
            ) as converted:
                result = list(csv.DictReader(converted, delimiter=";"))
            sensor_1039 = "sensor_1039__variable_3__Grados celcius [°C]"
            sensor_1041 = "sensor_1041__variable_3__Grados celcius [°C]"
            self.assertEqual(destination, Path(directory) / "history.wide.csv")
            self.assertEqual(measurements, 3)
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["fecha"], "2026-04-22T15:34:24")
            self.assertEqual(result[0][sensor_1039], "20.5")
            self.assertEqual(result[0][sensor_1041], "21.801")
            self.assertEqual(result[1]["fecha"], "2026-04-22T15:38:54")
            self.assertEqual(result[1][sensor_1039], "20.8")
            self.assertEqual(result[1][sensor_1041], "")

    def test_default_name_supports_plain_ndjson(self):
        self.assertEqual(
            default_csv_path(Path("history.ndjson")),
            Path("history.csv"),
        )
        self.assertEqual(
            default_csv_path(Path("history.ndjson.gz"), layout="wide"),
            Path("history.wide.csv"),
        )

    def test_expands_wildcards_for_powershell(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "a.ndjson.gz"
            second = Path(directory) / "b.ndjson.gz"
            first.touch()
            second.touch()

            self.assertEqual(
                expand_inputs([Path(directory) / "*.ndjson.gz"]),
                [first, second],
            )


if __name__ == "__main__":
    unittest.main()
