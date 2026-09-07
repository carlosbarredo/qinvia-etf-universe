# Metodología común

## Costes y deslizamientos

El proyecto adopta como especificación canónica la versión 1.0 del [QINVIA Historical Adaptive Cost and Slippage Model](methodology/HISTORICAL_ADAPTIVE_COST_AND_SLIPPAGE_MODEL.md).

Se aplicará a cualquier estudio o estrategia que cambie la exposición a uno o varios ETFs. El coste se carga sobre el cambio absoluto de exposición y utiliza la fecha efectiva de ejecución, el régimen histórico correspondiente y el bucket de volatilidad RV20 conocido antes de ejecutar.

La adopción mantiene congelados:

- Los tres tramos históricos de costes.
- Los buckets P10, Base, P65 y P90.
- El mínimo de 252 observaciones antes de abandonar Base.
- El desfase de una sesión entre señal y exposición efectiva.
- La sensibilidad `0.00×`, `0.50×`, `1.00×`, `1.50×` y `2.00×`.
- Los controles QA y las obligaciones de reporte.

Los gastos corrientes del ETF, roll yield, financiación, fiscalidad, impacto institucional y demás fricciones no se mezclarán con este coste all-in. Cuando se modelen, aparecerán como capas separadas y claramente etiquetadas para impedir el doble conteo.

La especificación fue concebida como modelo vehicle-agnostic para estudios del S&P 500. En este proyecto se adopta como convención común para ETFs; cualquier calibración específica por liquidez, bolsa, activo o vehículo deberá presentarse como análisis adicional y no sustituirá silenciosamente la versión 1.0.

## Criterio de comparación del universo público

El estudio conserva CAGR, Sortino, Calmar, Martin y Relative-Wealth Martin (RWM) en sus tablas descriptivas. Para evitar una decisión por votación entre ratios, la superioridad frente a SPY se determina principalmente comparando el RWM de cada ETF con el RWM de SPY sobre las mismas sesiones; CAGR se mantiene como contexto de crecimiento absoluto.

RWM se calcula sobre la riqueza fondo/cash. Cash queda fijado a FRED DFF, acumulado por días naturales, sin spread y con convención Actual/360, y después se muestrea en las sesiones del ETF. Sustituir cash por un benchmark riesgoso no forma parte de este procedimiento.
