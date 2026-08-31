# Datos del proyecto

- `raw/universe/`: archivos originales utilizados para descubrir y describir productos.
- `raw/market/`: respuestas originales de precios y eventos de mercado.
- `interim/`: catálogo normalizado, clasificaciones y datos sometidos a controles.
- `processed/`: datasets listos para análisis y versiones congeladas del universo.

Los datos originales son inmutables. Cualquier limpieza o reparación debe producir un archivo nuevo fuera de `raw/`.
