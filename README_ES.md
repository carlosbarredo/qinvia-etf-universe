# Universo ETF

**Un estudio bilingüe y reproducible sobre exposición, gestión intencional y por qué SPY es tan difícil de batir.** El proyecto construye un universo auditable con datos gratuitos, separa la beta estrecha de los productos que gestionan deliberadamente riesgo o selección y compara cada ETF maduro con SPY durante su propio historial común exacto.

[Estudio web](https://qinvia.com/es/research/etf-universe-exposure-skill) · [English](README.md) · [Informe en español](reports/etf_universe_1A/QINVIA_ETF_UNIVERSE_STUDY_1A.html) · [Informe en inglés](reports/etf_universe_1A/QINVIA_ETF_UNIVERSE_STUDY_1A_EN.html) · [Notebook en español](reports/etf_universe_1A/QINVIA_ETF_UNIVERSE_STUDY_1A.ipynb) · [Metodología](docs/METHODOLOGY.md) · [Procedencia de los datos](DATA.md)

## La evidencia, de un vistazo

La cohorte principal contiene **2.023 productos económicos** lanzados no más tarde del 1 de marzo de 2022, después de consolidar los alias históricos de ticker. Cada ETF se evalúa desde su primera sesión exacta común con SPY hasta el final del estudio.

- El **8,0%** supera a SPY en Relative-Wealth Martin (RWM), el criterio principal de eficiencia de trayectoria.
- El **4,6%** supera simultáneamente a SPY en RWM y CAGR.
- Entre **139** productos clasificados como gestión intencional, **15** superan el RWM de SPY y **7** lo hacen desde la mayoría de los puntos de entrada analizados.
- Después de igualar el capital final de SPY y cobrar financiación, **4 de 5** candidatos alcanzables conservan un RWM superior.

Los resultados no demuestran que toda exposición estrecha sea inútil ni que ningún proceso activo posea habilidad. Demuestran que exposición, eficiencia de trayectoria, capacidad e intención de gestión deben separarse antes de atribuir la superioridad a la gestión.

## Qué aporta el estudio

1. **Un embudo auditable.** Los productos se clasifican como `eligible`, `ineligible` o `review`, con motivos explícitos para excluir apalancamiento, exposición inversa, negociación de volatilidad y estructuras dependientes de la trayectoria.
2. **Controles de identidad.** Los alias históricos se consolidan para no contar un cambio de ticker como un producto económico nuevo.
3. **Una taxonomía completa.** Clase de activo, exposición, estrategia, sector, temática, geografía y estilo de gestión se mantienen por separado.
4. **Un único criterio decisorio principal.** CAGR, Sortino, Calmar, Martin y RWM permanecen visibles; la comparación con SPY se decide principalmente mediante RWM, con CAGR como contexto económico.
5. **Exposición frente a intención.** Se estudian por separado el mercado amplio, la beta sectorial o temática, las reglas sistemáticas y la gestión intencional.
6. **Pruebas de tensión.** Se incluyen estabilidad al punto de entrada, una escalera de apalancamiento con deuda fija, retorno igualado y sensibilidad al coste de financiación.

## Informes y evidencia reproducible

Los HTML son publicaciones autocontenidas con todas las figuras integradas. Los notebooks equivalentes conservan la narrativa, las fórmulas, las tablas y la evidencia derivada congelada.

| Idioma | Informe | Notebook |
|---|---|---|
| Español | [Abrir HTML](reports/etf_universe_1A/QINVIA_ETF_UNIVERSE_STUDY_1A.html) | [Abrir notebook](reports/etf_universe_1A/QINVIA_ETF_UNIVERSE_STUDY_1A.ipynb) |
| English | [Open HTML](reports/etf_universe_1A/QINVIA_ETF_UNIVERSE_STUDY_1A_EN.html) | [Open notebook](reports/etf_universe_1A/QINVIA_ETF_UNIVERSE_STUDY_1A_EN.ipynb) |

El repositorio incluye las tablas derivadas necesarias para inspeccionar los resultados publicados. No redistribuye los históricos brutos de Yahoo Finance ni el archivo fuente original de FRED DFF. Consulta [DATA.md](DATA.md).

## Instalación y pruebas

La adquisición está diseñada para Linux o WSL porque los recolectores autónomos utilizan bloqueos POSIX.

```bash
git clone https://github.com/carlosbarredo/qinvia-etf-universe.git
cd qinvia-etf-universe
python -m pip install -e ".[dev,research]"
python -m pytest
```

Las pruebas cubren clasificación, taxonomía, validación de históricos ajustados, métricas frente al benchmark, descriptores DBF, mecánica de apalancamiento y cálculo de RWM relativo a cash.

## Regeneración de la publicación

Después de adquirir los datos de los proveedores y producir las tablas descritas en [DATA.md](DATA.md):

```bash
PYTHONPATH=src python -m qinvia_etfs.universe_study
python scripts/build_etf_universe_study.py
```

El generador produce ambos idiomas desde una única fuente y deja los HTML y notebooks en `reports/etf_universe_1A/`.

## Alcance y limitaciones

- SPY es una referencia común deliberadamente exigente, no el benchmark natural de todos los mandatos.
- Yahoo Finance es útil y gratuito, pero sus símbolos, clasificaciones e históricos ajustados pueden cambiar.
- El catálogo conserva identidades históricas, pero la muestra disponible de fondos desaparecidos no es representativa; el survivorship bias sigue siendo material.
- RWM describe crecimiento y drawdown relativos a cash ya realizados. No revela apalancamiento, liquidez, capacidad, payoffs de opciones o tail risk no observado.
- El mecanismo de capacidad analizado es una hipótesis compatible con la literatura, no un resultado causal identificado por estos datos.
- El apalancamiento que iguala el retorno es un diagnóstico ex post, no una estrategia ejecutable.

## Cita, licencia y aviso

Los metadatos de cita están en [CITATION.cff](CITATION.cff). El código y la documentación original se publican con [licencia MIT](LICENSE). Los datos de terceros continúan sujetos a las condiciones de sus proveedores.

Qinvia · Carlos Barredo Lago · Investigación metodológica, no asesoramiento financiero.
