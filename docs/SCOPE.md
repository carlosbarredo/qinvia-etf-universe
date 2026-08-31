# Alcance y elegibilidad

## Objetivo

Estudiar productos cotizados cuyo propósito económico sea generar rentabilidad mediante una exposición larga o una estrategia de inversión. La elegibilidad se decide por la estructura y el objetivo del producto, nunca por la rentabilidad que haya obtenido posteriormente.

El catálogo será más amplio que la muestra de investigación. Esto permite conservar productos muertos, casos dudosos y categorías excluidas sin mezclarlos con el universo que se utilizará en los estudios.

## Unidad de observación

Un ticker no es una identidad permanente: puede cambiar, migrar de bolsa o ser reutilizado. El modelo distinguirá entre:

- `product_id`: identidad estable interna del producto.
- `listing_id`: una cotización concreta en una bolsa y moneda.
- `ticker`: símbolo utilizado por esa cotización durante un intervalo de fechas.

Cuando existan, se conservarán identificadores externos como SEC Series/Class ID, ISIN y CUSIP.

## Estados de elegibilidad

### `eligible`

En principio se incluyen:

- Renta variable, renta fija y monetarios.
- Inmobiliario e infraestructuras.
- Materias primas, incluidos petróleo, metales y productos agrícolas.
- Divisas y criptoactivos.
- ETFs activos, multiactivo, de factores y de dividendos.
- Estrategias de opciones cuyo objetivo principal sea inversión o generación de rentas, si no incorporan apalancamiento estructural relevante.
- Estrategias long/short, market neutral y absolute return, etiquetadas como `alternative_strategy`, siempre que no sean productos netamente short ni persigan un múltiplo de exposición.
- Managed futures, etiquetados como `alternative_strategy`, salvo variantes return-stacked o con apalancamiento estructural.

La forma jurídica se guardará por separado. Esto permite admitir ETF, ETC, grantor trust u otros ETP necesarios para representar materias primas sin confundirlos entre sí.

### `ineligible`

Se excluyen de la descarga histórica inicial:

- Productos inversos o short.
- Productos apalancados, tanto largos como inversos.
- Productos cuyo subyacente u objetivo principal sea VIX o volatilidad.
- Productos con reset diario y comportamiento deliberadamente multiplicado o inverso.
- Productos de payoff estructurado o dependiente de la trayectoria: defined outcome, buffer, autocallable, barrier, accelerated/target outcome y equivalentes.
- Estrategias return-stacked, capital-efficient o efficient-core con apalancamiento estructural incorporado.
- Productos cuyo objetivo principal sea protección de tail risk.
- Vehículos que no representen una inversión financiable o una serie de rentabilidad interpretable.
- Clases de fondos de inversión tradicionales capturadas por asociación con un trust ETF y símbolos que no sean cotizaciones válidas.
- Series registradas que el propio emisor mantiene como `Coming Soon` o para las que no existe ninguna evidencia gratuita de negociación. Permanecen catalogadas y pueden reabrirse si aparece una fuente positiva.
- Símbolos internos o indicativos de Yahoo con prefijo `^`, que pueden duplicar el nombre de un ETF pero no representan una cotización comprable del fondo.

Cada exclusión tendrá un `exclusion_reason`; no bastará con un booleano.

### `review`

Se enviarán a revisión únicamente los productos cuya identidad o existencia negociada no pueda resolverse con la información disponible. La falta conjunta de informe operativo SEC, historia de Yahoo y anuncio de lanzamiento permite clasificarlos como `registered_only_no_trading_evidence`, sin afirmar que jamás pudieran haber sido registrados o propuestos.

Un producto `review` permanece en el catálogo. No se descarga en la primera ejecución masiva, pero puede reclasificarse sin rehacer el universo.

La elegibilidad de la estrategia y la validación de la identidad se guardan por separado. Un producto actual confirmado por Nasdaq/Yahoo puede ser `eligible` y mantener `identity_status=current_listing_unlinked` hasta enlazarlo con su serie SEC histórica correcta.

Los candidatos históricos que ya son inequívocamente inversos o apalancados pueden conservar `identity_status=excluded_candidate_unvalidated`: la exclusión económica es firme aunque no se inviertan llamadas adicionales en demostrar si cada propuesta llegó a cotizar. Esto no constituye un pendiente del universo descargable.

## Campos mínimos del catálogo

- Identidad interna y ticker.
- Nombre, emisor, bolsa y moneda.
- Tipo jurídico o de producto.
- Categoría y exposición principal.
- Fecha de lanzamiento y fecha de cierre, cuando se conozcan.
- Estado: activo, liquidado, fusionado, cambiado de ticker o desconocido.
- Primera y última fecha en que fue observado por cada fuente.
- Estado de elegibilidad, motivo, reglas que coincidieron y nivel de confianza.
- Estado de validación de identidad, independiente de la elegibilidad económica.
- URL o referencia de la fuente y fecha de obtención.

## Orden de trabajo

1. Construir el catálogo con metadatos, sin descargar todavía todas las series de precios.
2. Generar un informe del espectro: tipos, categorías, activos/muertos y motivos de exclusión.
3. Revisar reglas y casos ambiguos.
4. Congelar una versión del universo elegible.
5. Descargar la historia de mercado de esa versión.

Así se reduce el volumen de llamadas a Yahoo, pero se conserva una pista auditable de todo lo encontrado y descartado.
