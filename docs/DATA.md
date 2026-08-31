# Datos y rentabilidad total

## Fuentes

### Precios y eventos

Yahoo Finance será el proveedor principal. El acceso se implementará inicialmente mediante `yfinance`, manteniendo el conector aislado para poder sustituirlo si fuera necesario.

### Universo y productos desaparecidos

El catálogo podrá combinar fuentes gratuitas como SEC, directorios de bolsas, páginas de emisores y anuncios de cierres. Ninguna de ellas se considerará perfecta por separado. Cada registro conservará procedencia y fecha de observación.

## Descarga diaria

Para cada listing elegible se solicitará la máxima historia diaria disponible. La descarga original conservará, cuando Yahoo los proporcione:

- `Open`, `High`, `Low`, `Close` y `Adj Close`.
- `Volume`.
- `Dividends`.
- `Stock Splits`.
- `Capital Gains`.
- Bolsa, zona horaria y moneda de cotización.
- Momento de descarga, versión del conector y resultado de la petición.

La configuración inicial será equivalente a:

```python
period="max"
interval="1d"
auto_adjust=False
actions=True
repair=False
```

`auto_adjust=False` es deliberado: necesitamos conservar simultáneamente precios sin ajustar y `Adj Close`. La descarga reparada de `yfinance`, si se utiliza, será una capa derivada y marcada; nunca sobrescribirá el original.

## Qué significa Total Return aquí

Yahoo no entrega un índice llamado `Total Return`. Entrega un cierre ajustado que incorpora los ajustes aplicables por splits y distribuciones. La serie principal de rentabilidad diaria será:

```text
total_return[t] = AdjClose[t] / AdjClose[t-1] - 1
```

Y el índice normalizado será:

```text
TR_index[t] = 100 × AdjClose[t] / primer_AdjClose_válido
```

Esto se denominará `yahoo_total_return` o `total_return_proxy`: representa reinversión implícita según los ajustes de Yahoo, antes de impuestos y sin costes de negociación. No se presentará como el NAV oficial del emisor.

También se conservarán dividendos, capital gains y splits para detectar inconsistencias y, cuando sea posible, reconstruir una segunda serie de control mediante reinversión de distribuciones.

## Liquidaciones y final de la serie

La desaparición de un ticker no implica una pérdida del 100 %, ni permite asumir que el último cierre es el valor final recibido. Los productos cerrados tendrán controles específicos:

- Buscar una distribución o pago de liquidación final.
- Comparar la última fecha negociada con la fecha oficial de cierre.
- Marcar si la rentabilidad terminal parece completa, incompleta o desconocida.
- No prolongar precios después de la fecha de desaparición.

## Calidad y trazabilidad

Se crearán indicadores, al menos, para:

- Serie vacía o ticker no encontrado.
- Huecos prolongados y duplicados.
- Moneda ausente o cambios aparentes de unidad.
- Precios o rendimientos extremos.
- Splits y distribuciones incompatibles con el ajuste.
- Primera y última fecha de datos.
- Posible reutilización de ticker.
- Historia terminal incompleta.
- Datos modificados por una reparación automática.

Las correcciones serán reproducibles y quedarán separadas de `data/raw/`.

## Formato previsto

- Parquet para tablas históricas y resultados grandes.
- CSV solo para intercambios pequeños o inspección manual.
- Una fila por `listing_id` y fecha en las series de mercado.
- Fechas de sesión en el calendario local de la bolsa, con metadatos de zona horaria conservados.
- Valores monetarios en la moneda de cotización; la conversión a una moneda común será una transformación posterior.

### Almacenamiento inicial de Yahoo

La capa descargada se guarda en `.local-wsl/market` o en la ruta WSL nativa indicada mediante `QINVIA_MARKET_WORK_ROOT`. Cada símbolo consultado produce:

- Un Parquet diario comprimido con ZSTD, con esquema versionado y escritura atómica.
- Un JSON de procedencia con consulta, cobertura temporal, filas, bolsa, moneda, zona horaria, tamaño y SHA-256.
- Una fila en el manifiesto reanudable.

La descarga física se deduplica por símbolo de Yahoo. La asignación a `product_id` se mantiene separada para evitar atribuir automáticamente una cotización reutilizada a una identidad histórica distinta.

## Política de actualización

La primera descarga será completa. Después se solicitará solo el tramo nuevo, incluyendo un pequeño solapamiento para detectar revisiones. Cada ejecución generará un manifiesto con éxitos, fallos y cobertura, y será segura de repetir.

## Tickers reutilizados

Una identidad histórica no se vincula a una serie solo porque comparta ticker.
Si Yahoo identifica hoy el símbolo como una acción, fondo mutuo u otro instrumento,
la serie se conserva en bruto pero se etiqueta `identity_mismatch` y no entra en
los estudios. Las excepciones requieren una evidencia curada en
`data/curated/market/identity_overrides.csv`.
