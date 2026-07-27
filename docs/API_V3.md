# Contrato de la API V3

V3 se agrega junto a los endpoints existentes. No elimina ni cambia rutas legacy.

## Consulta paginada

```http
GET /v3/dispositivos/224/mediciones
    ?fecha_inicio=2026-07-01
    &fecha_fin=2026-07-31
    &limite=500
    &cursor=CURSOR_OPCIONAL
```

La respuesta contiene `next_cursor`. Para continuar, se envía ese valor en la
siguiente solicitud. No se usa `OFFSET`. El cursor es opaco para el cliente y
representa la posición `(id_sensor, fecha, id_dato)`.

## Descarga NDJSON reanudable

```http
GET /v3/dispositivos/224/historico.ndjson
    ?fecha_inicio=2024-01-01
    &fecha_fin=2026-07-27
    &limite=500
```

El servidor resuelve los sensores asociados a `id_dispositivo`, consulta bloques
de hasta 1.000 filas y emite un checkpoint después de cada bloque:

```json
{"_meta":{"complete":false,"rows":500,"next_cursor":"..."}}
```

La última línea indica `complete: true`. El descargador conserva el último
checkpoint confirmado y puede reanudar tras un corte de red.

## Decisiones de seguridad operativa

- Fechas obligatorias.
- Límite máximo aplicado por el servidor.
- Consultas parametrizadas.
- Sin `COUNT(*)`, `OFFSET`, Pandas ni pivot.
- Una conexión y un dispositivo por descarga.
- Los endpoints legacy siguen disponibles durante la migración.

Pendiente antes de exposición pública definitiva: autenticación, autorización
por proyecto, rate limiting y trabajos asíncronos para exportaciones masivas.
