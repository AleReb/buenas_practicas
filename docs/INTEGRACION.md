# Integración y migración gradual

V3 se publica junto a los endpoints existentes y no obliga a sustituirlos en el
mismo despliegue. El contrato de `API_V3.md` puede montarse en cualquier servidor
HTTP o como un servicio separado detrás del mismo proxy.

## Secuencia recomendada

1. Implementar V3 sin cambiar las rutas legacy.
2. Validar resultados de ambos caminos con rangos pequeños.
3. Migrar consumidores uno por uno al identificador de dispositivo.
4. Medir duración, filas, errores y carga de base de datos.
5. Restringir consultas legacy que puedan recorrer todo el histórico.
6. Retirar V2 sólo cuando no existan consumidores activos.

## Configuración portable

La implementación debe recibir desde variables de entorno o un gestor de
secretos:

```text
DB_HOST
DB_PORT
DB_NAME
DB_USER
DB_PASSWORD
```

El servidor no debe fijar un esquema de producción en el código, aceptar nombres
de tabla desde parámetros HTTP ni registrar credenciales.

Cada lenguaje debe usar el pool de conexiones y la parametrización provistos por
su driver. En una descarga larga conviene reservar una conexión por stream o
usar una estrategia equivalente que preserve el orden de paginación.

## Proxy y plataforma

Para `/historico.ndjson`:

- desactivar buffering de respuesta;
- permitir transferencia por streaming;
- definir un timeout compatible con descargas largas;
- propagar la cancelación cuando el cliente se desconecta;
- aplicar límites de tamaño, concurrencia y velocidad.

La configuración exacta depende de Nginx, Apache, IIS, un API gateway, un
balanceador cloud o el servidor HTTP integrado.

## Protección temporal de V2

V2 puede seguir atendiendo consultas pequeñas. Las solicitudes legacy sin rango
de fechas y con resultados amplios deberían responder HTTP 422 e indicar la ruta
V3 recomendada. Esto evita que el JOIN antiguo recorra y ordene todo el
histórico.

## Ejemplo de la referencia Flask

Esta sección sólo aplica al archivo `historico_v3.py`; no forma parte del
contrato:

```python
import os

from historico_v3 import create_historico_v3_blueprint

config = {
    "user": os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "host": os.environ["DB_HOST"],
    "database": os.environ["DB_NAME"],
    "port": int(os.getenv("DB_PORT", "3306")),
}

app.register_blueprint(create_historico_v3_blueprint(config))
```

La implementación actual usa consultas MariaDB. Si se cambia el motor, deben
adaptarse el placeholder del driver y la expresión que suma un día a
`fecha_fin`, manteniendo el orden y el contrato HTTP.
