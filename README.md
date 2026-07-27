# Buenas prácticas para históricos de sensores

Referencia independiente del lenguaje para diseñar, implementar y consumir una
API de históricos por dispositivo. El contrato HTTP puede implementarse con
cualquier servidor, framework o lenguaje. Los programas Python incluidos son una
implementación ejecutable de referencia, no un requisito del protocolo.

## Modelo

Un **dispositivo** representa una estación o equipo y agrupa uno o más
**sensores**. Cada sensor puede producir distintas variables.

```text
dispositivo
  └── sensor
        └── variable
              └── mediciones
```

El cliente consulta usando `id_dispositivo`; el servidor resuelve internamente
los sensores asociados. Los elementos `224` y `225` de
`examples/dispositivos.example.json` son dispositivos, no sensores.

## Formatos generados

El flujo separa el archivo de transporte de los formatos de consumo:

| Formato | Orden | Uso recomendado |
|---|---|---|
| `.ndjson.gz` | sensor, fecha, dato | Respaldo compacto, auditoría y reanudación. |
| `.csv` largo | fecha, sensor, dato | Bases de datos, análisis y gráficos. |
| `.wide.csv` ancho | una fila por fecha | Excel y herramientas que esperan variables como columnas. |

El NDJSON conserva el orden que permite paginar eficientemente. Los CSV se
ordenan cronológicamente después de completar la descarga.

En el formato ancho, una columna se identifica por sensor y variable:

```text
sensor_1039__variable_3__Grados celcius [°C]
sensor_1041__variable_3__Grados celcius [°C]
```

Esto evita mezclar dos sensores que miden el mismo tipo de dato. Sólo se agrupan
mediciones con una fecha exactamente igual; una serie ausente produce una celda
vacía.

## Componentes

- `historico_v3.py`: servidor V3 de referencia mediante Flask.
- `download_v3.py`: descarga reanudable con checkpoints, reintentos y gzip.
- `ndjson_to_csv.py`: conversión independiente a CSV largo o ancho.
- `tests/`: pruebas automatizadas.

## Instalación

```powershell
cd C:\ruta\al\repositorio
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

En Linux o macOS:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

## Descarga con CSV cronológico

PowerShell:

```powershell
python .\download_v3.py `
  --device-id 225 `
  --start-date 2026-04-22 `
  --end-date 2026-07-27 `
  --output-dir .\descargas_completas `
  --csv
```

Linux o macOS:

```bash
python download_v3.py \
  --device-id 225 \
  --start-date 2026-04-22 \
  --end-date 2026-07-27 \
  --output-dir descargas_completas \
  --csv
```

El resultado contiene:

```text
descargas_completas/
  dispositivo-225_2026-04-22_2026-07-27.ndjson.gz
  dispositivo-225_2026-04-22_2026-07-27.csv
```

El CSV usa UTF-8 con BOM y `;` como separador para facilitar su apertura en
Excel configurado en español.

## Descarga con variables como columnas

```powershell
python .\download_v3.py `
  --device-id 225 `
  --start-date 2026-04-22 `
  --end-date 2026-07-27 `
  --output-dir .\descargas_completas `
  --csv `
  --csv-layout wide
```

El resultado ancho se guarda sin reemplazar el CSV largo:

```text
dispositivo-225_2026-04-22_2026-07-27.wide.csv
```

## Reanudar una descarga

Durante una interrupción se conservan:

```text
*.ndjson.part
*.state.json
```

Para continuar se ejecuta exactamente el mismo comando. No se deben borrar,
editar ni convertir esos archivos parciales. Cuando el servidor confirma
`complete: true`, el programa genera el `.ndjson.gz` definitivo y elimina los
temporales.

Si el archivo final ya existe, el descargador lo reutiliza y puede crear el CSV
sin consultar nuevamente todo el histórico.

## Convertir archivos existentes

CSV largo:

```powershell
python .\ndjson_to_csv.py `
  ".\descargas_completas\*.ndjson.gz"
```

CSV ancho:

```powershell
python .\ndjson_to_csv.py `
  ".\descargas_completas\*.ndjson.gz" `
  --layout wide
```

Otra carpeta de salida:

```powershell
python .\ndjson_to_csv.py `
  ".\descargas_completas\*.ndjson.gz" `
  --layout wide `
  --output-dir .\exportaciones_csv
```

El conversor procesa el histórico mediante almacenamiento temporal en disco, sin
cargar todas las mediciones en memoria. Primero escribe `.csv.part` y sólo
publica el CSV definitivo cuando termina correctamente.

## Evitar errores al copiar comandos

- No copie el indicador `PS C:\...>` de PowerShell.
- Ejecute un comando por vez y espere a que termine.
- En PowerShell, use el acento grave `` ` `` para continuar una línea.
- El acento grave debe ser el último carácter, sin espacios posteriores.
- En Linux y macOS se usa `\`; esa continuación no funciona en PowerShell.
- Si aparecen argumentos unidos, como `--csvpython`, presione `Ctrl+C` y vuelva
  a pegar únicamente un comando.

Las opciones disponibles se pueden consultar con:

```powershell
python .\download_v3.py --help
python .\ndjson_to_csv.py --help
```

## Verificación

```powershell
python -m unittest discover -s tests -v
```

Las pruebas cubren cursores, fechas, bloqueos transitorios de Windows,
conversión, orden cronológico y formato ancho.

## Documentación

- [`docs/API_V3.md`](docs/API_V3.md): contrato HTTP, cursores, orden y errores.
- [`docs/IMPLEMENTACION_SERVIDOR.md`](docs/IMPLEMENTACION_SERVIDOR.md):
  algoritmo y SQL para cualquier backend.
- [`docs/CLIENTES.md`](docs/CLIENTES.md): clientes con cURL, JavaScript,
  Python, PHP y Go.
- [`docs/DESCARGAS_Y_CSV.md`](docs/DESCARGAS_Y_CSV.md): descarga, reanudación,
  CSV largo, pivot ancho y reglas multilenguaje.
- [`docs/INTEGRACION.md`](docs/INTEGRACION.md): migración gradual desde rutas
  legacy.

## Portabilidad

El mismo procedimiento puede implementarse con JavaScript/Node.js, Java, .NET,
Go, PHP, Python u otro lenguaje:

1. Leer el NDJSON línea por línea.
2. Confirmar checkpoints `_meta`.
3. Reanudar mediante el cursor opaco.
4. Conservar el NDJSON.GZ como fuente.
5. Ordenar por fecha para consumo.
6. Generar CSV largo o pivot ancho mediante streaming y almacenamiento temporal.

MariaDB es el motor de la referencia. La paginación keyset puede trasladarse a
otros motores SQL adaptando placeholders y operaciones de fecha.

## Escala y seguridad

Para históricos de varios años o muchos dispositivos se recomiendan trabajos
asíncronos, particiones por fecha y almacenamiento de objetos. Una página web no
debería descargar cientos de miles de filas si sólo necesita un gráfico
resumido.

Antes de una exposición pública deben añadirse autenticación, autorización por
proyecto, rate limiting, límites de concurrencia y observabilidad.
