# Rendimiento del motor V6

La optimización conserva las matrices físicas y la búsqueda de resonancias.
Prepara una vez por frecuencia las propiedades Miki y los términos de cada
hoja, usa aritmética compleja escalar para localizar raíces y NumPy para integrar
lotes de ángulos. Las capas y cámaras idénticas reutilizan su matriz durante cada
evaluación angular. La caché de cuadraturas Gauss–Legendre ya existía en V5.
No se sustituyó la integración por una malla uniforme que pueda saltarse modos
estrechos.

## Medición reproducible

El registro completo está en `validation/v6-performance.json`. Ambos motores
se ejecutaron secuencialmente en el mismo proceso, Python 3.13.5, Linux x86-64,
con un hilo OpenBLAS. El motor V5 se exportó del commit `eda1a77`.

| Caso | V5 | V6 | Aceleración | Diferencia máxima TL |
|---|---:|---:|---:|---:|
| Quad, 21 bandas, campo difuso, modelo infinito | 112.08 s | 19.98 s | 5.61× | 0.0 dB |

Caso sintético: cuatro hojas iguales de 10 kg/m², D = 434.0277778 N·m,
η = 0.03; tres cámaras de 100 mm, cada una con 50 mm de relleno Miki y
resistividad 10 000 Pa·s/m². El ángulo máximo es 78° y las bandas abarcan
50–5000 Hz. Los tiempos son una observación de este equipo compartido, no una
promesa para cualquier equipo o configuración. La igualdad de TL verifica la
optimización de este caso; no valida experimentalmente esos valores ni convierte
una construcción de hojas independientes en una construcción con montantes.

Para repetir la comparación desde la raíz del repositorio (Bash):

```sh
git show eda1a77:src/noiz_transmission/core/transfer.py > /tmp/transfer_v5.py
OPENBLAS_NUM_THREADS=1 uv run python scripts/benchmark_solver.py \
  --panels 4 --timeout 180 --legacy-module /tmp/transfer_v5.py \
  --output /tmp/noiz-performance.json
```

Para medir todos los casos de V6 en PowerShell:

```powershell
$env:OPENBLAS_NUM_THREADS = "1"
uv run python scripts/benchmark_solver.py --timeout 180 --repeat 2 --output rendimiento-v6.json
```

La opción `--finite` mide el nuevo modelo con paneles de 2.4 × 2.7 m. No se
compara su curva directamente con V5 porque cambia el modelo físico. El script
acepta `--bands 125 500 1600 4000` para una comprobación breve. Un timeout activa
la cancelación cooperativa y registra el caso incompleto como error, sin tratarlo
como un tiempo de cálculo terminado.

## Controles numéricos

La tolerancia solicitada distribuye un presupuesto de error estimado entre la
integración angular y la de frecuencia. Es una estimación numérica, no una cota
rigurosa ni un margen de precisión experimental. Se conservan las pruebas de
resonancias estrechas de Double, Triple y Quad que invalidaban la convergencia
aparente de mallas uniformes, y se añaden equivalencia del kernel preparado,
gases evanescentes, evaluación Miki una sola vez por medio y cancelación activa.

Las hojas finitas añaden puntos de integración en los cambios del límite Davy.
El cálculo finito conserva su integral sin normalizar por ese límite. Su
verificación independiente se recoge en `tests/test_transfer_finite.py`.
