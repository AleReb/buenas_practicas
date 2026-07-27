# Contrato HTTP de la API V3

Este documento define comportamiento observable por HTTP. No obliga a usar un
lenguaje, framework, servidor web ni biblioteca de base de datos específicos.

## Convenciones

- Ruta base de ejemplo: `https://api.example.com/v3`.
- Fechas: `YYYY-MM-DD`, interpretadas según la zona horaria definida por el
  servicio.
- El intervalo incluye todo `fecha_inicio` y todo `fecha_fin`.
- JSON usa UTF-8.
- `id_dispositivo`, `id_sensor` e `id_dato` son identificadores enteros.
- Un dispositivo puede contener cualquier cantidad positiva de sensores.
- El cliente nunca necesita enviar la lista de sensores.

## Consulta paginada

```http
GET /v3/dispositivos/{id_dispositivo}/mediciones
    ?fecha_inicio=2026-04-22
    &fecha_fin=2026-04-22
    &limite=500
    &cursor=CURSOR_OPCIONAL
Accept: application/json
```

Parámetros:

| Nombre | Obligatorio | Descripción |
|---|---:|---|
| `id_dispositivo` | Sí | Dispositivo que agrupa los sensores. |
| `fecha_inicio` | Sí | Primer día incluido. |
| `fecha_fin` | Sí | Último día incluido. |
| `limite` | No | Filas solicitadas; el servidor aplica su máximo. |
| `cursor` | No | Posición opaca recibida en la página anterior. |

Respuesta exitosa:

```json
{
  "status": "success",
  "data": {
    "dispositivo": {
      "id_dispositivo": 224,
      "codigo_interno": "ESTACION-01",
      "id_proyecto": 18,
      "descripcion": "Estación de ejemplo"
    },
    "mediciones": [
      {
        "id_dato": 90001,
        "id_dispositivo": 224,
        "id_sensor": 1028,
        "id_variable": 53,
        "fecha": "2026-04-22T12:23:19",
        "fecha_insercion": "2026-04-22T12:23:20",
        "valor": 0.0,
        "variable_descripcion": "Dióxido de azufre",
        "unidad": "ppm"
      }
    ],
    "next_cursor": "WzEwMjgs...",
    "has_more": true
  }
}
```

Para solicitar la página siguiente se repiten el dispositivo, las fechas y el
límite, y se envía `next_cursor` como `cursor`. El cursor se trata como una
cadena opaca: el cliente no debe interpretarlo, modificarlo ni construirlo.

`has_more: false` termina la paginación. `next_cursor` puede ser `null` cuando no
hay resultados adicionales.

## Orden garantizado

Al concatenar todas las páginas, las mediciones V3 están ordenadas
lexicográficamente por:

```text
id_sensor ASC, fecha ASC, id_dato ASC
```

Este es el **orden de transporte**. Permite reanudar mediante el cursor y recorrer
el índice sin usar `OFFSET`. No es un orden cronológico global: al comenzar el
siguiente sensor, `fecha` puede ser anterior a la última fecha del sensor
precedente.

Un consumidor no debe asumir que el NDJSON está ordenado sólo por fecha. Para
Excel, gráficos o análisis temporal se recomienda crear una salida derivada con:

```text
fecha ASC, id_sensor ASC, id_dato ASC
```

El reordenamiento se hace después de completar la descarga. No se debe modificar
el orden de las filas todavía no confirmadas ni construir un cursor desde el
orden del CSV.

Las implementaciones que usen fechas con diferentes zonas u offsets deben
normalizarlas a una referencia común antes de ordenar. Comparar fechas como texto
sólo es seguro cuando todas usan la misma representación ISO 8601 y zona horaria.

## Descarga NDJSON reanudable

```http
GET /v3/dispositivos/{id_dispositivo}/historico.ndjson
    ?fecha_inicio=2026-04-22
    &fecha_fin=2026-04-22
    &limite=500
Accept: application/x-ndjson
```

Cada medición ocupa una línea JSON. Después de uno o más bloques, el servidor
emite una línea de control:

```json
{"_meta":{"complete":false,"rows":500,"next_cursor":"WzEwMjgs..."}}
```

La última línea confirma el final:

```json
{"_meta":{"complete":true,"rows":1734,"next_cursor":null}}
```

Reglas para reanudar:

1. El cliente escribe las mediciones recibidas en un archivo temporal.
2. Sólo confirma bytes y filas al recibir una línea `_meta`.
3. Si la conexión se corta, descarta los bytes posteriores al último checkpoint.
4. Repite la solicitud con el último `next_cursor` confirmado.
5. Publica o comprime el archivo únicamente después de `complete: true`.

Una línea `_error` indica que el streaming no pudo continuar:

```json
{"_error":{"status":503,"message":"error consultando la base de datos"}}
```

Los clientes deben revisar `_error` aunque la cabecera HTTP ya se haya enviado
con estado 200, porque un error puede ocurrir después de iniciar el stream.

## Errores JSON

Antes de iniciar un stream, los errores usan esta forma:

```json
{"status":"fail","error":"fecha_inicio es obligatorio"}
```

Estados recomendados:

| HTTP | Uso |
|---:|---|
| 400 | Parámetros, fechas, límite o cursor inválidos. |
| 401 | Falta autenticación. |
| 403 | El usuario no puede consultar el proyecto o dispositivo. |
| 404 | El dispositivo no existe o no tiene sensores asociados. |
| 422 | Solicitud legacy insegura que debe migrar a V3. |
| 429 | Límite de solicitudes o descargas concurrentes excedido. |
| 503 | Base de datos o dependencia temporalmente no disponible. |

## Compatibilidad

Agregar campos JSON es un cambio compatible: los clientes deben ignorar campos
desconocidos. Renombrar o eliminar campos, cambiar tipos o alterar la semántica
del cursor requiere una nueva versión de la API.

Los endpoints V3 pueden convivir con rutas legacy; no es necesario reemplazarlas
en el mismo despliegue.

El orden de transporte también forma parte del contrato. Cambiarlo a
`fecha, id_sensor, id_dato` sin cambiar la versión invalidaría los cursores
existentes y podría producir filas omitidas o duplicadas.
