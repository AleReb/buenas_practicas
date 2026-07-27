# Clientes en varios lenguajes

Los ejemplos usan variables para evitar acoplar la documentación a un servidor
concreto. Sustituya la URL, el dispositivo y las fechas.

## cURL

Consulta paginada:

```bash
curl --get "$API_URL/v3/dispositivos/$DEVICE_ID/mediciones" \
  --data-urlencode "fecha_inicio=$START_DATE" \
  --data-urlencode "fecha_fin=$END_DATE" \
  --data-urlencode "limite=500" \
  --header "Accept: application/json"
```

Descarga NDJSON:

```bash
curl --fail-with-body --no-buffer --get \
  "$API_URL/v3/dispositivos/$DEVICE_ID/historico.ndjson" \
  --data-urlencode "fecha_inicio=$START_DATE" \
  --data-urlencode "fecha_fin=$END_DATE" \
  --data-urlencode "limite=500" \
  --header "Accept: application/x-ndjson" \
  --output historico.ndjson
```

Guardar la salida de cURL no implementa por sí solo checkpoints ni reanudación.

## JavaScript

Compatible con navegadores modernos y Node.js 18 o posterior:

```javascript
const url = new URL(
  `/v3/dispositivos/${deviceId}/mediciones`,
  apiUrl,
);
url.search = new URLSearchParams({
  fecha_inicio: startDate,
  fecha_fin: endDate,
  limite: "500",
});

const response = await fetch(url, {
  headers: { Accept: "application/json" },
});
if (!response.ok) {
  throw new Error(`HTTP ${response.status}: ${await response.text()}`);
}

const body = await response.json();
for (const measurement of body.data.mediciones) {
  console.log(measurement.id_sensor, measurement.fecha, measurement.valor);
}
```

Para recorrer todas las páginas, conserve `body.data.next_cursor`, agréguelo a
los parámetros y repita mientras `body.data.has_more` sea verdadero.

## Python

```python
import requests

url = f"{api_url}/v3/dispositivos/{device_id}/mediciones"
params = {
    "fecha_inicio": start_date,
    "fecha_fin": end_date,
    "limite": 500,
}

while True:
    response = requests.get(url, params=params, timeout=(15, 60))
    response.raise_for_status()
    data = response.json()["data"]

    for measurement in data["mediciones"]:
        print(
            measurement["id_sensor"],
            measurement["fecha"],
            measurement["valor"],
        )

    if not data["has_more"]:
        break
    params["cursor"] = data["next_cursor"]
```

`download_v3.py` contiene una implementación más completa para NDJSON,
reintentos, checkpoints y compresión.

## PHP

Ejemplo con la extensión cURL:

```php
<?php
$query = http_build_query([
    'fecha_inicio' => $startDate,
    'fecha_fin' => $endDate,
    'limite' => 500,
]);
$url = rtrim($apiUrl, '/')
    . "/v3/dispositivos/{$deviceId}/mediciones?{$query}";

$handle = curl_init($url);
curl_setopt_array($handle, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_HTTPHEADER => ['Accept: application/json'],
    CURLOPT_TIMEOUT => 60,
]);
$raw = curl_exec($handle);
if ($raw === false) {
    throw new RuntimeException(curl_error($handle));
}
$status = curl_getinfo($handle, CURLINFO_RESPONSE_CODE);
curl_close($handle);

if ($status < 200 || $status >= 300) {
    throw new RuntimeException("HTTP {$status}: {$raw}");
}
$body = json_decode($raw, true, flags: JSON_THROW_ON_ERROR);
```

## Go

```go
endpoint, err := url.Parse(
    fmt.Sprintf("%s/v3/dispositivos/%d/mediciones", apiURL, deviceID),
)
if err != nil {
    return err
}
query := endpoint.Query()
query.Set("fecha_inicio", startDate)
query.Set("fecha_fin", endDate)
query.Set("limite", "500")
endpoint.RawQuery = query.Encode()

request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.String(), nil)
if err != nil {
    return err
}
request.Header.Set("Accept", "application/json")

response, err := http.DefaultClient.Do(request)
if err != nil {
    return err
}
defer response.Body.Close()
if response.StatusCode < 200 || response.StatusCode >= 300 {
    return fmt.Errorf("API returned %s", response.Status)
}
```

## Autenticación

El repositorio no impone un método. En producción, el servidor puede requerir
OAuth 2.0, JWT, una API key o identidad de servicio. Esa credencial se transmite
según la política del despliegue y nunca debe incorporarse directamente al
código fuente.
