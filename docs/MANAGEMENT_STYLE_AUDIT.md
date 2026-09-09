# Auditoría completa de `management_style`

## Resultado

La revisión contrasta las **2.022** filas previas al filtro estricto de producto del estudio 1A y produce una decisión
uno a uno. Quedan **0** productos como `not_determined`. La evidencia se
conserva por fila en el resultado local y las excepciones se mantienen en un
registro versionado con fuente primaria.

| Estilo asignado | Productos |
| --- | ---: |
| `index_passive_identified` | 1.452 |
| `non_index_management_identified` | 279 |
| `active_identified` | 204 |
| `systematic_or_rules_based` | 33 |
| `static_exposure_or_trust` | 26 |
| `not_applicable_security` | 17 |
| `mixed_or_changed_mandate` | 11 |
| **Total** | **2.022** |

`non_index_management_identified` no significa dato ausente. N-CEN confirma
que el producto no se declara index fund pero esa respuesta no demuestra por
sí sola gestión discrecional. Esta categoría evita convertir automáticamente
un `IS_INDEX` negativo en gestión activa.

`systematic_or_rules_based` se reserva para una clasificación de gestión
realmente adecuada a productos mecánicos no indexados. Un proceso sistemático
puede existir dentro de un ETF legalmente activo; cuando el emisor lo confirma
la etiqueta principal es `active_identified` y el carácter sistemático queda
como atributo de estrategia.

## Qué cambió frente a la taxonomía inicial

La taxonomía anterior se basaba en gran medida en palabras del nombre. La
auditoría cambia 1.500 filas en total: las 1.017 antes indeterminadas y 483 de
las 1.005 ya etiquetadas.

Los cambios más relevantes entre productos antes asignados son:

| Revisión | Productos |
| --- | ---: |
| Sistemático por nombre → índice confirmado | 387 |
| Sistemático por nombre → activo confirmado | 63 |
| Sistemático por nombre → mandato mixto | 8 |
| Índice por nombre → activo confirmado | 7 |
| Índice por nombre → valor sin estilo ETF aplicable | 9 |
| Activo por nombre → índice confirmado | 5 |
| Activo por nombre → mandato mixto | 3 |

La revisión conserva como activos —con documentación de sus emisores— los ETF
de ARK Invest, Avantis, Capital Group, Dimensional, Davis, AdvisorShares,
T. Rowe Price y otras gamas activas. Esto corrige el error conceptual de tratar
un proceso cuantitativo o por reglas como sinónimo de fondo indexado.

## Jerarquía de evidencia

1. **SEC Form N-CEN C.3.** Se usan ocho trimestres desde 2024q3 hasta 2026q2.
   `SHARES_OUTSTANDING.tsv` enlaza ticker con `FUND_ID` y
   `FUND_REPORTED_INFO.tsv` aporta `SERIES_ID`, `IS_ETF` e `IS_INDEX`.
2. **Identidad legal.** El `sec_series_id` del catálogo tiene prioridad sobre
   el ticker. La continuidad de nombre protege frente a ticker reuse y un
   registro posterior incompleto no borra una respuesta anterior válida.
3. **Fuente primaria del emisor o SEC.** Resuelve productos fuera de N-CEN y
   corrige o refina casos donde la condición legal de gestión no puede
   deducirse de C.3. Se admite una fuente de gama cuando enumera o cubre de
   forma inequívoca todos los productos de esa familia.

Cobertura por fuente:

| Fuente | Productos |
| --- | ---: |
| SEC N-CEN C.3 | 1.727 |
| Decisión documentada con fuente primaria | 295 |

1.975 decisiones tienen confianza alta y 47 confianza media. Estas últimas
son principalmente casos N-CEN no indexados en los que la documentación
disponible no permite afirmar con rigor si la implementación es discrecional
o mecánica; siguen siendo decisiones explícitas y auditables.

## Historias con cambio de mandato

Once series abarcan periodos materialmente distintos de indexación pasiva y
gestión activa:

| Ticker | Fecha de conversión a activa |
| --- | --- |
| WTV | 18 diciembre 2017 |
| DGRE | 19 octubre 2018 |
| WTMF | 4 junio 2021 |
| AIVI | 18 enero 2022 |
| AIVL | 18 enero 2022 |
| BTAL | febrero 2022 |
| SQLV | 10 mayo 2022 |
| DSTL | 3 abril 2023 |
| JSMD | 12 mayo 2025 |
| JSML | 12 mayo 2025 |
| RVNU | 4 agosto 2026 |

Estas filas reciben `mixed_or_changed_mandate`. No deben contarse como gestión
activa sobre todo su historial ni como pasivas sobre todo su historial. Una
atribución de habilidad exige cortar la serie en la fecha documentada.

## Casos que exigieron atención especial

- **JAAA** queda `active_identified`: Janus Henderson lo describe como ETF
  activo que invierte principalmente en deuda CLO con calificación AAA.
- **ARB, IZRL, KMLM, LVHB y MNA** pasan de activos inferidos por nombre a
  `index_passive_identified` por evidencia regulatoria u oficial.
- **ACSI, BITS, LCR, SAGP, SAMT, STNC y TMFG** presentaban campos N-CEN
  incompletos; se resolvieron con documentación del emisor.
- **GEX** tiene ticker reutilizado. El histórico corresponde al antiguo ETF
  indexado de VanEck y no al producto Cambria posterior.
- **BEMO** corresponde al mandato indexado histórico; en noviembre de 2019
  cambió de nombre y ticker a ADME junto con el paso a gestión activa.
- **PLTM** arrastraba un `sec_series_id` de la identidad histórica FTAG. La
  evidencia del emisor confirma que es un trust físico de platino.
- **SCCD** es una nota corporativa y **SWZ** un fondo cerrado. Junto con los
  ETN detectados reciben `not_applicable_security` y deben excluirse de una
  cohorte estrictamente ETF.

## Archivos y reproducción

- Lógica: `src/qinvia_etfs/management_style.py`
- Ejecución: `scripts/audit_management_styles.py`
- Evidencia versionada: `docs/evidence/management_style_overrides.csv`
- Resultado público: `artifacts/etf-universe/management_style_audit.csv`
- Resumen público: `artifacts/etf-universe/management_style_audit_summary.json`
- Fuente que debe readquirirse: datasets SEC N-CEN de 2024q3 a 2026q2.

Para reproducir desde la raíz del repositorio:

```bash
python scripts/audit_management_styles.py
python -m pytest tests/test_management_style.py
```

Los ZIP N-CEN y los resultados derivados están ignorados por Git. Deben
obtenerse de los [datasets de Form N-CEN de la SEC](https://www.sec.gov/data-research/sec-markets-data/form-n-cen-data-sets).
El repositorio público distribuye la lógica, los tests y el registro de
decisiones y fuentes; no redistribuye los archivos fuente SEC ni los datos
Yahoo locales.

## Riesgos metodológicos restantes

- N-CEN es autorreportado y contesta la condición de index fund. No mide la
  proporción de decisiones humanas y mecánicas ni demuestra habilidad.
- `active_identified` describe la estructura de gestión documentada y no una
  conclusión sobre alfa o calidad del gestor.
- Las páginas del emisor pueden moverse. El registro conserva la explicación
  pero una futura publicación debería archivar los documentos utilizados.
- El enlace por ticker nunca basta ante una reutilización. La identidad legal
  y la continuidad de la serie económica prevalecen.
