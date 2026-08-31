# Ejecución autónoma en WSL

El recolector del universo se ejecuta de manera independiente de Codex y de cualquier terminal visible.

## Alcance de este proceso

Esta ejecución solo:

1. recopila metadatos del universo;
2. fusiona identidades actuales e históricas;
3. clasifica `eligible`, `ineligible` y `review`; y
4. genera el informe del espectro.

No descarga precios ni calcula rentabilidades.

## Ubicaciones

- Trabajo y archivos brutos en WSL: `.local-wsl/` por defecto, o una ruta externa definida mediante `QINVIA_UNIVERSE_WORK_ROOT` y `QINVIA_MARKET_WORK_ROOT`.
- Código y documentación: la raíz del clon `qinvia-etf-universe`.
- Resultados derivados: `data/interim/universe` y `data/processed/universe`.

Los archivos brutos permanecen en WSL. Esto reduce el coste de entrada/salida sobre la carpeta compartida y permite reutilizar descargas si se repite el proceso.

## Tolerancia a fallos

- Cada fuente se escribe primero en un archivo temporal y se publica mediante renombrado atómico.
- Los archivos válidos ya descargados se reutilizan.
- Existe un bloqueo para impedir dos ejecuciones simultáneas.
- El estado y el registro se guardan en `runtime/` dentro del área WSL.
- Los límites temporales de la SEC activan una pausa y un reintento controlado.
- Un fallo de una fuente queda reflejado como advertencia en el informe; no se oculta.

## Resultados

- `catalog.csv`: catálogo completo de identidades encontradas.
- `eligible_universe.csv`: candidatos para la futura descarga de precios.
- `review_queue.csv`: casos que requieren revisión.
- `universe_report.md`: espectro y recuentos.
- `run_manifest.json`: procedencia, versión de reglas, duración y advertencias.

## Reclasificación sin red

Cuando cambian únicamente las reglas de elegibilidad, el catálogo existente puede reclasificarse en WSL sin volver a consultar las fuentes ni descargar precios:

```bash
cd /ruta/al/clon/qinvia-etf-universe
PYTHONPATH=src python3 scripts/reclassify_universe.py
```

El proceso actualiza de forma atómica el catálogo, el universo elegible, la cola de revisión, el informe y el manifiesto.

## Recolector autónomo de precios

El histórico diario se ejecuta con `scripts/launch_market_wsl.sh` y se consulta con `scripts/market_status_wsl.sh`. Por defecto, los Parquet grandes se guardan en `.local-wsl/market`; puede apuntarse a un sistema de archivos WSL nativo mediante `QINVIA_MARKET_WORK_ROOT`. En Windows se refleja solo el estado compacto en `runtime/market_collector_status.json`.

Características operativas:

- Una petición y un Parquet por símbolo único de Yahoo.
- Reanudación por símbolo sin repetir archivos ya verificados.
- Separación entre éxito, ausencia de historia y error recuperable.
- Reintentos con enfriamiento ante limitaciones temporales.
- Piloto inicial representativo de 100 símbolos dentro de la propia ejecución completa.
- Estimación de finalización actualizada tras cada símbolo.
- Manifiesto, registro, PID y bloqueo residentes en WSL.

## Validación de identidades históricas

La cola histórica se contrasta con informes operativos/listados de la SEC y con precios de Yahoo dentro de la ventana temporal observada. Los resultados se guardan en `historical_identity_audit.csv`. Solo la evidencia positiva se promociona automáticamente al archivo curado `data/curated/universe/identity_overrides.csv`; la ausencia de resultados no se interpreta por sí sola como que el producto nunca se lanzó.

```bash
PYTHONPATH=src python3 scripts/audit_historical_candidates.py
PYTHONPATH=src python3 scripts/apply_identity_audit.py
PYTHONPATH=src python3 scripts/reclassify_universe.py
```

## Validación de mercado y comparación con SPY

Una vez finalizada la descarga, `scripts/analyze_vs_spy_wsl.sh` valida esquema,
filas y SHA-256 de cada Parquet elegible. Después separa los tickers de Yahoo
reutilizados por instrumentos ajenos al ETF y calcula las métricas descriptivas
frente a SPY sobre las mismas sesiones desde el primer dato comparable.

Los resultados pequeños se exportan a `data/processed/market`; los históricos
brutos permanecen en WSL.
