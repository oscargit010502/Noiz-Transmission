# V6 · tamaño finito, pérdidas de borde y rendimiento

Versión `0.6.0`. Los proyectos nuevos del editor seleccionan la aproximación de
tamaño finito; los archivos anteriores conservan su modelo infinito al abrirse.
Los 3.629 registros del catálogo permanecen incluidos en el código descargable
y en el paquete Python, sin importación inicial.

## Modelo y límites

Single, Double, Triple y Quad admiten la integración angular finita dependiente
de ancho y alto. Se usa la formulación publicada por Hansen a partir de Davy.
Las pérdidas estructurales adicionales de borde se editan por panel y se guardan
con el proyecto. Su valor inicial es cero para no inventar las pérdidas de un
montaje ni duplicar las ya incluidas en el material.

La aplicación conserva el cálculo de placas isotrópicas, coincidencia, cámaras
de gas, absorbente Miki y transmisión energética en tercios de octava. La
integración se optimiza preparando las propiedades que se repiten a cada ángulo
y reutilizando matrices idénticas. Se mantiene la detección de resonancias y
la verificación de convergencia. La interfaz conserva en memoria un número
limitado de resultados completos para proyectos idénticos, incluida su procedencia.

La corrección de Davy no es la formulación de Sewell ni resuelve los modos
estructurales a baja frecuencia. La referencia de rigidez de Hansen se ofrece
como función científica independiente, sin unirla artificialmente a la curva.
La extensión del corte angular a varias hojas es una aproximación propia, no
el modelo de pared doble de Davy. Las uniones por montantes, impacto y lluvia
continúan fuera del motor disponible.

Se indica qué bandas quedan parcial o totalmente bajo `1.5 f11`, usando la
primera frecuencia simplemente apoyada como diagnóstico. Si esas bandas
afectan al rango de un índice, no se presenta ese Rw o STC como resultado
principal. El espectro extrapolado sigue disponible para inspección.

No se ha establecido un margen experimental de error para este motor. Los
ejemplos de Barron verifican frecuencias características y una clasificación
STC publicada; no se presentan como validación experimental del predictor.
Los artículos identificados para validar casos reales se distinguen de los
textos efectivamente consultados.

## Probar y reproducir

En Windows, extrae el ZIP de la rama `codex/noiz-transmission-v6` y abre
`INICIAR_NOIZ.cmd`. La carpeta debe contener `pyproject.toml`. El lanzador
mantiene `UV_LINK_MODE=copy` para instalaciones dentro de OneDrive.

Los ejemplos `examples/v6_single.noiz.json`, `v6_double.noiz.json`,
`v6_triple.noiz.json` y `v6_quad.noiz.json` usan placas sintéticas, hojas
independientes y condiciones explícitas. No son soluciones comerciales ensayadas.

```sh
uv sync --locked --all-extras
uv run noiz assembly examples/v6_single.noiz.json --output-dir artifacts/v6
uv run python scripts/benchmark_solver.py --finite --timeout 120
uv run pytest
```

El esquema de proyecto 4 conserva la elección de modelo y las pérdidas de borde.
V6 abre esquemas 1–3 mediante migraciones explícitas; las versiones antiguas no
pueden abrir el esquema 4. Guarda una copia al convertir proyectos.

## Documentación científica

- [Ecuaciones, pérdidas y dominio de aplicación](v6-physics.md).
- [Revisión de los tres libros, páginas y atribuciones](v6-reference-review.md).
- [Evidencia y comprobaciones independientes](v6-evidence.md).
- [Mediciones reproducibles de rendimiento](../validation/v6-performance.md).
- [Guía para probarlo en Windows](../PROBAR_EN_WINDOWS.md).

## Verificación de la entrega

En Linux, Python 3.13.5, se ejecutó `pytest -W error --tb=short -q`:
**775 pruebas aprobadas**, sin omisiones. Ruff y `git diff --check` limpios.
Single, Double, Triple y Quad se calcularon desde los cuatro archivos V6 y
exportaron JSON, CSV y HTML con 21 bandas. Sus valores Rw sintéticos fueron
30, 47, 51 y 53; sirven para comprobar este ejemplo, no para acreditar un sistema.

El paquete Python se construyó e instaló fuera del checkout: abrió la interfaz
Qt, cargó los 3.629 registros sin biblioteca externa, calculó 21 bandas con
`finite-davy-transfer-1`, mostró el contorno de referencia y recuperó un segundo
cálculo idéntico desde caché. Las pruebas Qt se ejecutaron con la plataforma
`offscreen`; esta sesión no acredita una ejecución nativa en Windows.
