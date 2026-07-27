# Descargas y exportación a CSV

Este procedimiento separa el formato de transporte del formato de consumo:

- **NDJSON.GZ** es el archivo fuente compacto y reanudable.
- **CSV** es una copia derivada para Excel, análisis y herramientas gráficas.

Se recomienda conservar ambos. El CSV se puede volver a crear; el archivo fuente
permite verificar o reprocesar los datos sin consultar nuevamente el servidor.

## Flujo recomendado

1. Elegir un dispositivo y un rango explícito de fechas.
2. Descargar mediante checkpoints hasta recibir `complete: true`.
3. Comprimir y publicar el archivo final `.ndjson.gz`.
4. Convertir a `.csv` sólo después de completar la descarga.
5. Registrar cantidad de filas, dispositivo, rango y fecha de exportación.
6. Validar fechas mínima y máxima, sensores presentes y valores inesperados.

Nunca se debe crear el CSV definitivo desde un `.part`: podría representar una
descarga incompleta.

## Descargar y convertir automáticamente

```bash
python download_v3.py \
  --device-id 224 \
  --start-date 2026-04-22 \
  --end-date 2026-07-27 \
  --output-dir descargas_completas \
  --csv
```

Al terminar se conservan:

```text
descargas_completas/
  dispositivo-224_2026-04-22_2026-07-27.ndjson.gz
  dispositivo-224_2026-04-22_2026-07-27.csv
```

Si la descarga se interrumpe, se ejecuta exactamente el mismo comando. El
programa reanuda desde el último checkpoint. Si el `.ndjson.gz` final ya existe,
lo reutiliza y sólo crea el CSV faltante.

Para Excel en español se usa `;` como separador y UTF-8 con BOM. Otro separador
se puede solicitar explícitamente:

```bash
python download_v3.py \
  --device-id 224 \
  --start-date 2026-04-22 \
  --end-date 2026-07-27 \
  --output-dir descargas_completas \
  --csv \
  --csv-delimiter ","
```

## Orden de las filas

El NDJSON se descarga en el orden técnico:

```text
id_sensor, fecha, id_dato
```

Ese orden permite paginar eficientemente en la base de datos, pero hace que la
fecha parezca retroceder cuando comienza el siguiente sensor.

El CSV usa por defecto el orden de consumo:

```text
fecha, id_sensor, id_dato
```

Así, todas las mediciones quedan en una única línea temporal. Las columnas
también se organizan empezando por dispositivo, sensor, variable, unidad, fecha
y valor.

Para conservar el orden por sensor:

```bash
python ndjson_to_csv.py historico.ndjson.gz --sort-by sensor
```

Para conservar exactamente el orden recibido:

```bash
python ndjson_to_csv.py historico.ndjson.gz --sort-by original
```

Con descarga y conversión automática se usa `--csv-sort-by`:

```bash
python download_v3.py \
  --device-id 224 \
  --start-date 2026-04-22 \
  --end-date 2026-07-27 \
  --output-dir descargas_completas \
  --csv \
  --csv-sort-by fecha
```

## Formato largo y formato ancho

El formato largo conserva una medición por fila:

```text
fecha                id_sensor  variable       valor
2026-04-22T15:34:24  1039       Temperatura    20.5
2026-04-22T15:34:24  1039       Humedad        46.7
```

Es apropiado para bases de datos, herramientas analíticas y gráficos que filtran
por variable.

El formato ancho o pivot usa una fila por dispositivo y fecha:

```text
fecha                sensor_1039__...Temperatura  sensor_1039__...Humedad
2026-04-22T15:34:24  20.5                          46.7
```

Se genera con:

```bash
python ndjson_to_csv.py \
  descargas_completas/*.ndjson.gz \
  --layout wide
```

O directamente después de descargar:

```bash
python download_v3.py \
  --device-id 225 \
  --start-date 2026-04-22 \
  --end-date 2026-07-27 \
  --output-dir descargas_completas \
  --csv \
  --csv-layout wide
```

El archivo ancho usa el nombre `*.wide.csv`, por lo que no reemplaza el CSV
largo.

Cada columna se identifica con sensor, variable, descripción y unidad:

```text
sensor_1039__variable_3__Grados celcius [°C]
sensor_1041__variable_3__Grados celcius [°C]
```

Incluir `id_sensor` evita mezclar dos instrumentos que miden la misma variable.
Sólo se combinan mediciones cuya `fecha` sea exactamente igual. Si una serie no
tiene medición en ese instante, la celda queda vacía. No se deben aproximar
horarios ni rellenar valores sin una regla de negocio explícita.

## Convertir archivos existentes

Un archivo:

```bash
python ndjson_to_csv.py ruta/al/historico.ndjson.gz
```

Varios archivos:

```bash
python ndjson_to_csv.py descargas_completas/*.ndjson.gz
```

Otra carpeta de salida:

```bash
python ndjson_to_csv.py \
  descargas_completas/*.ndjson.gz \
  --output-dir exportaciones_csv
```

También acepta NDJSON sin compresión:

```bash
python ndjson_to_csv.py historico.ndjson
```

El conversor:

- procesa el archivo sin cargar todas las mediciones en memoria;
- ordena cronológicamente usando una base SQLite temporal en disco;
- descubre las columnas presentes;
- puede producir formato largo o pivot ancho;
- conserva caracteres Unicode;
- serializa objetos o arreglos anidados como JSON dentro de la celda;
- ignora líneas `_meta`;
- detiene la conversión si encuentra `_error` o JSON inválido;
- escribe primero `.csv.part` y publica el CSV sólo al terminar.

El ordenamiento temporal mantiene bajo el consumo de memoria, pero necesita
espacio libre en disco y puede tardar con históricos muy grandes. La base SQLite
temporal se elimina al finalizar.

## Reglas para implementaciones en otros lenguajes

Un descargador compatible, sin importar el lenguaje, debería:

1. Leer NDJSON línea por línea.
2. Diferenciar mediciones, `_meta` y `_error`.
3. Confirmar bytes únicamente después de `_meta`.
4. Reanudar con `next_cursor`, sin inventar ni modificar el cursor.
5. No publicar archivos parciales como resultados completos.
6. Escribir el CSV mediante streaming y escape estándar de comillas y separadores.
7. Representar valores nulos como celdas vacías.
8. Mantener identificadores como texto o enteros sin notación científica.
9. Usar UTF-8 y declarar el delimitador elegido.
10. Ordenar la salida de consumo por fecha sin cambiar el cursor del transporte.
11. Conservar el archivo fuente o un checksum para auditoría.

## Equivalencias por lenguaje

El procedimiento no requiere Python. Estas piezas están disponibles en las
bibliotecas estándar o habituales de cada plataforma:

| Plataforma | HTTP streaming | Gzip y lectura por línea | JSON | Escritura CSV | Ordenamiento grande |
|---|---|---|---|---|---|
| JavaScript/Node.js | `fetch` y streams | `zlib`, `readline` | `JSON.parse` | stream o biblioteca CSV | SQLite temporal o mezcla de bloques |
| Java | cliente HTTP y `InputStream` | `GZIPInputStream`, `BufferedReader` | biblioteca JSON elegida | escritor CSV | base temporal o mezcla externa |
| .NET/C# | `HttpClient` | `GZipStream`, `StreamReader` | `System.Text.Json` | escritor CSV | SQLite temporal o archivos ordenados |
| Go | `net/http` | `compress/gzip`, `bufio` | `encoding/json` | `encoding/csv` | SQLite o mezcla de bloques |
| PHP | cURL con callback | `gzopen`, `gzgets` | `json_decode` | `fputcsv` | `SQLite3` o archivos temporales |
| Python | `requests` | `gzip` | `json` | `csv` | `sqlite3` o mezcla de bloques |

Los nombres concretos cambian, pero el estado mínimo es el mismo:

```text
cursor confirmado
bytes confirmados
filas confirmadas
descarga completa
```

Regla de reanudación:

```text
al recibir una medición:
    escribirla como pendiente

al recibir _meta:
    sincronizar archivo
    guardar cursor, bytes y filas de forma atómica

si la conexión falla:
    truncar hasta los últimos bytes confirmados
    solicitar de nuevo usando el cursor confirmado
```

Regla de ordenamiento:

```text
entrada estable:  id_sensor, fecha, id_dato
salida analítica: fecha, id_sensor, id_dato
```

Cuando todas las fechas no comparten formato y zona horaria, cada implementación
debe analizarlas como instantes y normalizarlas antes de comparar.

## CSV para páginas web

Los históricos pequeños pueden publicarse como CSV junto al HTML y JavaScript.
Para cientos de miles de filas es preferible generar archivos por mes,
dispositivo o variable, o crear resúmenes horarios/diarios. Una página no debería
descargar todo el histórico si sólo necesita mostrar un gráfico reducido.
