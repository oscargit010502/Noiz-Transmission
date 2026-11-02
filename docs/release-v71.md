# V7.1 · frame resuelto y cálculo automático

Versión `0.7.1`, construida sobre V7. El usuario selecciona el frame, las hojas,
la cámara y el relleno. El modo automático resuelve las hipótesis internas del
puente estructural sin exigir una compliancia, calibre de correlación o
separación de tornillos. La consulta **Detalles del frame…** es de solo lectura.

## Actualización de resultados

La partición Single inicial se calcula al abrir. Abrir un archivo, crear un
proyecto y cambiar material, espesor, cantidad, frame, cámara o relleno también
actualiza los resultados. Una pausa de 200 ms agrupa pulsaciones y permite
escribir números sin tener que pulsar Enter. F5 conserva el refresco manual.

Hay un solo trabajo activo. Una edición cancela el anterior y programa la última
composición; una respuesta tardía nunca se presenta como resultado de la nueva.
Las entradas incompletas o incompatibles muestran un aviso en línea y vuelven a
calcular al corregirse. Buscar productos sin seleccionarlos, girar la vista o
cambiar Rw/STC no lanza un cálculo físico. Las comparaciones guardadas se conservan.

## Modelo Double y decisiones internas

La identidad del nuevo modelo es `davy-air-sharp-bridge-1`. Combina la vía aérea
Davy/Hansen con una vía de puentes rígidos basada en Sharp (1978):

- Montantes compartidos ordinarios: contacto lineal. Tener tornillos separados
  no convierte un ala continua en apoyos puntuales.
- Uniones puntuales entre ambas hojas identificadas explícitamente: impedancias
  de Sharp 17, 20 y 22. No se interpreta automáticamente un clip sobre montante
  como dos contactos puntuales.
- Hojas sin conexión común: se omite el puente entre ellas. Montantes alternados
  con soleras compartidas no se declaran automáticamente independientes.
- Conectores sin caracterización: contacto lineal genérico, con esa limitación
  en el informe. No se inventa una mejora de aislamiento por marca, resorte o elastómero.

Se suman coeficientes de transmisión, no TL en decibelios. La región inferior
conserva una sola respuesta de masa total; la transición se reconstruye hacia
la suma de caminos, evitando contar la misma respuesta dos veces. La resonancia
mostrada es la física masa–aire–masa, no la transición empírica `113/√(mₑd)` de
Sharp ni una constante ajustada a la captura de INSUL.

El relleno conserva su espesor real. Se prioriza una resistividad explícita del
proyecto o del catálogo en SI. Si falta, se utiliza **20.000 Pa·s/m²** de la fibra
de referencia de Hansen, tabla 7.12, p. 442. No se deduce ese valor de la densidad
ni del `Damping` del XML. Para un medio no fibroso sin datos se identifica
expresamente que se está sustituyendo por la fibra de referencia.

La absorción Miki cambia de forma continua con el espesor, también por debajo
de 50 mm. La ruta nueva conserva una envolvente de pérdidas de fondo
`α = min(kd, max(0,1, α_Miki))` para evitar que un relleno tendiendo a cero suprima
el amortiguamiento de la cámara vacía. Es una hipótesis de ingeniería explícita,
no una corrección publicada atribuida a Davy. La ruta histórica V7 queda igual
cuando no se solicita esta opción nueva.

Las resoluciones de frame y absorbente, sus valores y fuentes quedan incluidas
en JSON, CSV y HTML. La geometría seleccionada sigue disponible en el proyecto.

## Alcance de la mejora

La eliminación de entradas avanzadas no significa disponer de la rigidez medida
de cada producto. **El acero delgado sigue siendo una aproximación rígida** en
el modo automático. Hansen distingue expresamente su flexibilidad de la hipótesis
rígida apropiada para madera. Dos frames con iguales parámetros y contactos
genéricos pueden dar el mismo resultado; no se afirma precisión específica para
un perfil comercial ni un límite inferior universal del TL.

El ejemplo de doble hoja conserva la caída de coincidencia por la vía aérea;
no se impone una curva de pendientes perfectas ni se ajusta a los puntos de la
imagen aportada. La continuación de la asíntota de puente por esa región sigue
siendo una aproximación. Las verificaciones de ecuaciones no demuestran una
tolerancia experimental de la combinación.

Single conserva el motor finito V7. Triple/Quad conserva V6 para hojas
independientes. Esta entrega no añade impacto, lluvia, Sewell modal, flancos
ni una caracterización dinámica de aisladores.

Fuentes y pruebas: [revisión bibliográfica](v71-reference-review.md),
[verificación independiente](v71-validation.md).

## Probar y reproducir

Descarga el [ZIP V7.1](https://github.com/oscargit010502/Noiz-Transmission/archive/refs/heads/codex/noiz-transmission-v7-1.zip),
extráelo en una carpeta nueva y ejecuta `INICIAR_NOIZ.cmd`. Abre
`examples/v71_double_steel.noiz.json`: ya se calcula sin F5. El ejemplo no
contiene compliancia ni resistividad de entrada. También están disponibles
`v71_double_timber.noiz.json` y `v71_single.noiz.json`.

Los ejemplos Double usan hojas sintéticas de 12,7 mm, cámara de 89 mm,
montantes cada 600 mm y relleno de referencia de 50 mm; no son fichas ni
ensayos de fabricante. Los archivos anteriores preservan su modelo. En una
doble pared antigua, **Frame → Usar V7.1** realiza la conversión explícita.
El guardado utiliza esquema 6; conserva una copia si necesitas abrir el
archivo con una versión anterior.

```sh
uv sync --locked --all-extras
uv run noiz assembly examples/v71_single.noiz.json examples/v71_double_steel.noiz.json examples/v71_double_timber.noiz.json --output-dir artifacts/v71
uv run python scripts/benchmark_v7.py --example-prefix v71 --repeats 5
```

La entrega pasó **917 pruebas** en Linux con Qt offscreen y advertencias
tratadas como errores. Incluyen inicio automático, edición sin Enter, cancelación,
último resultado válido, apertura/nuevo proyecto, migración V7, Qty 0,
resolución de contactos, reciprocidad, suma energética y ecuaciones independientes.
Ruff y `git diff --check` pasan. Estas pruebas no sustituyen la comprobación
nativa en Windows ni una validación acústica en laboratorio.

También se construyeron wheel y sdist. El wheel instalado fuera del repositorio
carga los 3.629 registros, calcula el Single inicial y recalcula la doble pared
al cambiar su relleno, sin pulsar Calcular. Los tres ejemplos exportan JSON,
CSV y HTML con el modelo y los parámetros internos resueltos.

Los tiempos de los tres ejemplos, sin interfaz, espera de edición, caché ni
exportación, se conservan en [v71-performance.json](../validation/v71-performance.json).
Son mediciones de casos concretos y no una garantía para cualquier sistema.
