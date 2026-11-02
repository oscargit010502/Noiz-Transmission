# V7 · doble pared con montantes y resultados simultáneos

Versión `0.7.0`, construida sobre V6.1. El cambio principal es el cálculo de
Double con transmisión aérea y por montantes de madera o acero. La interfaz
mantiene los controles nativos compactos y muestra la tabla al lado del gráfico.

## Motor y datos necesarios

Single utiliza integración angular finita y energética de bandas, con pérdidas
de material y borde explícitas. Para una hoja homogénea añade el límite de
espesor de Ljunggren/Hansen evaluado en centros de banda. No se suma otra
corrección de radiación que duplique la carga acústica existente.

Double usa las expresiones Davy/Hansen de resonancia modificada, transmisión
aérea y transmisión por conexiones. Se suman coeficientes de transmisión,
no índices Rw ni valores TL en dB. La ruta Double evalúa las aproximaciones
publicadas por centros de tercios; no equivale a la integración de la ruta Single.
Sus cambios de régimen se documentan en las advertencias del resultado.

Para madera se modelan conexiones puntuales rígidas. Para acero se declara
flexibilidad puntual en m/N o lineal en m²/N y separación de fijaciones. El
modo automático elige conexión puntual o lineal según longitud de onda de
flexión. Una conversión entre flexibilidades supone distribución uniforme de
fijaciones, no una medición de la unión.

La correlación experimental por calibre no se toma como calibración verificada:
la fuente consultada no precisa la convención del parámetro `g`. No se convierte
el espesor del XML en ese parámetro. Los ejemplos usan flexibilidad explícita,
con valor sintético declarado, para que el procedimiento sea reproducible.

Para rellenos se introduce resistividad y espesor, o absorción efectiva de
cámara. La aproximación Miki de absorción difusa con respaldo rígido es una
sustitución de ingeniería de la absorción de cámara; no es una caracterización
experimental del sistema ni una conversión del campo Damping del catálogo.
La API del núcleo también ofrece la hipótesis explícita de fibra mineral
adecuada ≥50 mm descrita en Hansen; no se activa por reconocer una marca.

Los bastidores separados se idealizan sin puentes comunes. Los montantes
alternados con soleras compartidas no se transforman automáticamente en esa
configuración. Triple/Quad conserva la ruta V6 de hojas independientes;
V7 no extiende sin justificación las fórmulas Double a más hojas con montantes.

## Referencias, correcciones y límites

Se consultaron el capítulo 7 de Bies/Hansen/Howard/Hansen, 6.ª edición,
y el capítulo 11 de Vér/Beranek. La revisión identifica una referencia cruzada
inconsistente entre radiación forzada y radiación mecánica; el camino por
montantes utiliza la segunda, con ecuaciones y elección documentadas.

- Tamaño finito: corrección angular de Davy; no se renombra como Sewell.
- Pérdidas de borde: explícitas y separadas de pérdidas ya incluidas en el material.
- Espesor: límite de alta frecuencia de Ljunggren; no es un solucionador completo
  de cortante, Mindlin o Lamb.
- Davy/Sharp: no se introduce una mezcla arbitraria para producir una curva
  aparentemente experimental. La coincidencia depende de rigidez y pérdidas.
- Precisión: no se declara margen en dB ni equivalencia con Strutt o INSUL.

La consulta directa a `https://strutt.arup.com/help/` devolvió un bloqueo de
la política de red del entorno de desarrollo. Se dejó preparado el dominio
en el borrador de configuración, pendiente de aplicar. La correspondencia
exacta con su página Transmission Loss Prediction y sus fuentes primarias
queda pendiente; esta entrega atribuye sus fórmulas a las fuentes consultadas.

Véanse [revisión de fuentes](v7-reference-review.md) y
[verificaciones y datos publicados](v7-validation.md).

## Interfaz y render

Gráfico y tabla TL se consultan juntos; la leyenda se conserva a la derecha
y encima de la tabla. No hay zoom ni desplazamiento de ejes por ratón o teclado.
La tabla puede desplazarse para consultar todas las bandas.

La vista del elemento incorpora aristas negras visibles con prueba de profundidad,
sin diagonales de triangulación ni líneas de objetos ocultos a través de placas
opacas. Se distinguen montantes, soleras abiertas y relleno. Los símbolos de
resortes, neopreno y Sylomer conservan la indicación **esquemático, no BIM**:
sus proporciones y posiciones ilustrativas no determinan parámetros acústicos.

## Probar y reproducir

Extrae el [ZIP V7](https://github.com/oscargit010502/Noiz-Transmission/archive/refs/heads/codex/noiz-transmission-v7.zip)
en una carpeta nueva y abre `INICIAR_NOIZ.cmd`. Abre uno de estos archivos y
pulsa **F5**:

- `examples/v7_single.noiz.json`
- `examples/v7_double_timber.noiz.json`
- `examples/v7_double_steel.noiz.json`

Los ejemplos Double incluyen dos hojas sintéticas de 12,5 mm, cámara de
100 mm, absorbente de 40 mm con resistividad 10.000 Pa·s/m², montantes cada
600 mm y fijaciones cada 300 mm. El de acero declara flexibilidad puntual
de 10 µm/N como supuesto de demostración. Ninguno es una ficha comercial ensayada.

```sh
uv sync --locked --all-extras
uv run noiz assembly examples/v7_double_steel.noiz.json --output-dir artifacts/v7-steel
uv run python scripts/benchmark_v7.py --repeats 5
```

El esquema 5 guarda los nuevos parámetros. Al abrir esquemas anteriores se
conserva su modelo; seleccionar V7 es una decisión explícita. Las versiones
anteriores no pueden abrir los nuevos proyectos de esquema 5.

## Rendimiento medido

En este entorno Linux/Python 3.13, la mediana de cinco cálculos completos por
ejemplo fue 0,181 s para Single, 0,00291 s para Double madera y 0,00285 s para
Double acero. Se calculan 21 bandas, incluyendo validación de entradas; se
excluyen interfaz, caché y escritura de informes. Los tiempos y resultados
individuales están en [v7-performance.json](../validation/v7-performance.json).

Son casos sintéticos concretos, no una garantía de rendimiento en otros equipos
ni una comparación de velocidad entre fórmulas físicas equivalentes a V6.

## Comprobaciones de entrega

- 847 pruebas aprobadas en Linux con Qt offscreen y advertencias como errores;
  Ruff y `git diff --check` sin incidencias.
- Los tres ejemplos V7 exportan JSON, CSV y HTML con 21 bandas y parámetros
  reproducibles, conservando las limitaciones del modelo en el informe.
- Paquetes wheel y sdist construidos. La instalación del wheel fuera del
  repositorio abre Qt, carga los 3.629 materiales integrados y calcula el
  ejemplo Double acero: Rw 41 / STC 40, con tabla y gráfico visibles juntos.
- Las pruebas gráficas cubren 1024×680, 1366×768 y 1366×980; no sustituyen
  una ejecución nativa de Windows, que no se ha realizado en este entorno.
