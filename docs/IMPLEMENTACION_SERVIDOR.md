# Implementación del servidor

Esta guía describe el algoritmo, no una tecnología concreta. La implementación
Python de `historico_v3.py` sirve como ejemplo ejecutable.

## Responsabilidades

Para cada solicitud, el servidor debe:

1. Validar dispositivo, fechas, límite y cursor.
2. Autorizar el acceso al proyecto y al dispositivo.
3. Resolver los sensores asociados al dispositivo.
4. Consultar mediciones mediante paginación keyset.
5. Serializar la respuesta JSON o NDJSON sin cargar todo el histórico en memoria.
6. Cerrar conexión, cursor y stream aun cuando el cliente se desconecte.

## Esquema mínimo

Los nombres pueden adaptarse al modelo de cada sistema:

```text
dispositivos
  id_dispositivo (PK)

sensores_en_dispositivo
  id_dispositivo
  id_sensor

datos
  id_dato (PK)
  id_sensor
  fecha
  valor
```

Índices recomendados:

```text
sensores_en_dispositivo (id_dispositivo, id_sensor)
datos (id_sensor, fecha, id_dato)
```

Si el motor no permite incluir `id_dato` en el índice, `(id_sensor, fecha)` sigue
siendo útil, pero debe medirse el costo de ordenar los empates.

El nombre del esquema o base de datos debe venir de configuración. No se deben
concatenar nombres proporcionados por el usuario ni imprimir credenciales en
logs.

## Consulta keyset

Primero se obtienen los sensores:

```sql
SELECT id_sensor
FROM sensores_en_dispositivo
WHERE id_dispositivo = ?
ORDER BY id_sensor;
```

La primera página usa fechas obligatorias y un límite acotado:

```sql
SELECT id_dato, id_sensor, fecha, valor
FROM datos
WHERE id_sensor IN (?, ?, ...)
  AND fecha >= ?
  AND fecha < ?
ORDER BY id_sensor, fecha, id_dato
LIMIT ?;
```

El límite superior debe ser el inicio del día posterior a `fecha_fin`. La
función exacta para calcularlo cambia entre MariaDB, PostgreSQL, SQL Server,
Oracle y otros motores; también puede calcularse en la aplicación.

Las páginas siguientes agregan:

```sql
AND (
  id_sensor > ?
  OR (
    id_sensor = ?
    AND (
      fecha > ?
      OR (fecha = ? AND id_dato > ?)
    )
  )
)
```

Todos los valores se envían como parámetros del driver. Los signos `?` son
marcadores conceptuales; cada biblioteca usa su propia sintaxis.

## Cursor

El cursor representa:

```text
(id_sensor, fecha, id_dato)
```

Para el cliente es opaco. El servidor puede:

- codificar el arreglo como JSON y Base64 URL-safe;
- firmarlo con HMAC para detectar modificaciones;
- cifrarlo si no desea revelar identificadores;
- guardar un token aleatorio asociado a estado temporal.

En servicios públicos se recomienda firmar el cursor e incluir en la firma el
dispositivo, el rango de fechas y la versión del formato. Un cursor válido no
reemplaza la autorización.

## Streaming

No se debe materializar todo el histórico antes de responder. El servidor lee un
bloque, emite sus filas, emite el checkpoint y continúa desde el cursor.

El proxy inverso debe permitir streaming y tener buffering desactivado para esta
ruta. También deben configurarse timeouts, compresión y límites de concurrencia
acordes al tamaño esperado.

## Escala y operación

- Evitar `OFFSET`, `COUNT(*)`, pivots y listas de sensores enviadas por el cliente.
- Limitar filas por bloque y descargas simultáneas por usuario o proyecto.
- Registrar duración, filas emitidas, reintentos y desconexiones, nunca secretos.
- Usar réplicas de lectura si la consistencia requerida lo permite.
- Para rangos de varios años, crear un trabajo asíncrono y entregar un archivo
  desde almacenamiento de objetos.
- Probar planes de ejecución con volúmenes representativos.

## Adaptación por plataforma

La ruta puede implementarse, por ejemplo, con:

- Node.js: Express, Fastify, NestJS o APIs nativas.
- Java: Spring Boot, Jakarta REST o Micronaut.
- .NET: ASP.NET Core.
- Go: `net/http`, Gin o Echo.
- PHP: Laravel, Symfony o PSR-7.
- Python: Flask, FastAPI o Django.

La elección no cambia el contrato descrito en `API_V3.md`.
