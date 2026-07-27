# Buenas prácticas para históricos de sensores

Referencia independiente del lenguaje para diseñar, implementar y consumir una
API de históricos por dispositivo. El contrato HTTP puede implementarse en
cualquier servidor o framework; los archivos Python de este repositorio son una
implementación de ejemplo, no un requisito del protocolo.

## Modelo

Un **dispositivo** representa una estación o equipo y puede agrupar uno o más
**sensores**. El cliente consulta por `id_dispositivo`; el servidor resuelve
internamente todos los `id_sensor` asociados.

Los elementos `224` y `225` de `examples/dispositivos.example.json` son dos
dispositivos de ejemplo, no dos sensores. Cada respuesta de mediciones identifica
el sensor de origen mediante `id_sensor`.

## Qué se puede reutilizar

- El contrato HTTP, los cursores y el formato NDJSON no dependen de Python.
- El NDJSON usa un orden técnico reanudable; el CSV derivado usa un orden
  cronológico apropiado para personas, gráficos y análisis.
- El servidor puede implementarse con Java, JavaScript/TypeScript, Go, C#,
  PHP, Python, Ruby u otro lenguaje.
- El cliente puede ser una aplicación web, un proceso batch, una herramienta de
  línea de comandos o un servicio.
- MariaDB es la base usada por la referencia. El patrón de paginación keyset se
  puede trasladar a otros motores SQL ajustando su sintaxis de fechas.

## Documentación

- [`docs/API_V3.md`](docs/API_V3.md): contrato HTTP completo y errores.
- [`docs/IMPLEMENTACION_SERVIDOR.md`](docs/IMPLEMENTACION_SERVIDOR.md):
  algoritmo y SQL de referencia para cualquier backend.
- [`docs/CLIENTES.md`](docs/CLIENTES.md): ejemplos con cURL, JavaScript,
  Python, PHP y Go.
- [`docs/DESCARGAS_Y_CSV.md`](docs/DESCARGAS_Y_CSV.md): procedimiento
  recomendado para descargar, reanudar, verificar y convertir a CSV.
- [`docs/INTEGRACION.md`](docs/INTEGRACION.md): migración gradual desde rutas
  legacy y ejemplo específico de Flask.

## Implementación Python de referencia

- `historico_v3.py`: servidor V3 como Blueprint de Flask.
- `download_v3.py`: descargador con checkpoints, reintentos y gzip.
- `ndjson_to_csv.py`: conversor independiente de NDJSON o NDJSON.GZ a CSV.
- `tests/`: pruebas unitarias.

Instalación:

```bash
python -m venv .venv
```

En Linux o macOS:

```bash
. .venv/bin/activate
pip install -r requirements.txt
```

En PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Ejemplo de descarga. Se deben reemplazar el dispositivo y las fechas por valores
que existan en el servidor:

```bash
python download_v3.py \
  --device-id 224 \
  --start-date 2026-04-22 \
  --end-date 2026-04-22 \
  --output-dir descargas \
  --csv
```

El descargador procesa el dispositivo completo sin que el usuario tenga que
enumerar sus sensores. Durante una caída conserva `.part` y `.state.json`; al
completar genera `.ndjson.gz` y elimina los temporales.

Con `--csv` también genera un archivo `.csv` cronológico, separado por punto y
coma y codificado para Excel. El `.ndjson.gz` se conserva como respaldo compacto.

Un archivo existente también se puede convertir sin volver a descargar:

```bash
python ndjson_to_csv.py descargas/dispositivo-224_2026-04-22_2026-04-22.ndjson.gz
```

## Estado y alcance

Esta primera fase cubre consulta paginada y streaming reanudable. Para
exportaciones de varios años o muchos dispositivos se recomienda crear trabajos
asíncronos y entregar el resultado desde almacenamiento de objetos.

Antes de una exposición pública deben añadirse autenticación, autorización por
proyecto, rate limiting, observabilidad y límites de concurrencia.
