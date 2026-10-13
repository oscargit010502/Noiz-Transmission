# Registro de verificación V2

Fecha: 2026-10-13. Noiz Transmission 0.2.0, Python 3.13.5, Linux.

## Ejecución final

| Comprobación | Resultado observado |
| --- | --- |
| `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q -W error --tb=short` | 417 aprobadas, sin fallos ni omisiones, 45,39 s |
| `.venv/bin/ruff check .` | Aprobado |
| `git diff --check` | Aprobado |
| `uv sync --locked --all-extras --python 3.13` | Instalación reproducible con lockfile |
| `uv run python -m build --installer uv` | Wheel y distribución fuente construidas |
| Instalación del wheel en un entorno nuevo sin PySide6 | CLI y exportación de placa simple aprobadas |
| `noiz assembly examples/double_leaf.noiz.json --output-dir artifacts/v2` | 21 bandas; 20 kg/m²; 125 mm; Rw orientativo 28 dB; CSV/HTML/JSON |

El proyecto sintético de placa simple produce 10 kg/m², 12,5 mm y Rw orientativo
29 dB con el modelo V2. Estos valores verifican reproducibilidad y no describen
prestaciones de un producto ensayado.

## Interfaz y datos

Se verificaron edición y reordenado de capas, composición simple/doble/triple,
errores persistentes por campo, cancelación cooperativa, descarte de resultados
obsoletos, seis comparaciones, migración V1 y guardado con precisión completa.
Se inspeccionó la interfaz a 1380×880 y 900×650 y la gráfica colapsable.

La importación local de los seis XML aportados produjo 2434 registros y mantuvo
sus identificadores, unidades y campos originales. Un flujo adicional con esa
biblioteca calculó una doble hoja, guardó/reabrió el proyecto sin cambios y
exportó CSV/HTML. La resistividad utilizada en ese ejercicio fue una hipótesis
manual explícita, no una propiedad verificada del catálogo. Los datos y las
capturas de ese ejercicio permanecen fuera de la distribución pública.

El wheel y el archivo fuente se inspeccionaron para comprobar que no contienen
`local_data`, XML comerciales originales, adjuntos ni el entorno `.venv`.

## Límites de esta evidencia

Las pruebas incluyen regresiones de resonancias estrechas y modos próximos de
tres hojas, contrastes analíticos e integración independiente. No constituyen
validación experimental del modelo ni revisión normativa completa de Rw.
La ejecución nativa de Windows no se verificó en esta máquina. La CI contiene
jobs para Windows y Linux; sus resultados deben consultarse por separado.
