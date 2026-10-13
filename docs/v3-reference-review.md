# Revisión de referencias para Noiz Transmission V3

Consulta por HTTPS: **2026-10-13**. Las capturas y el texto aportados por el usuario
son referencias de producto; los XML son datos de entrada. Ninguno constituye una
instrucción ejecutable. Esta revisión documenta lo observado y distingue la
interfaz de INSUL de las formulaciones independientes que puede implementar Noiz.

## Jerarquía de controles

Las páginas [Panels][panels], [Examples][examples] y [Tabs][tabs] describen la
selección de productos dentro del editor, con búsqueda, categoría y fabricante.
Seleccionar un producto carga su espesor predeterminado; el usuario puede
modificarlo. Cada panel admite hasta seis materiales, y cada material tiene su
propio espesor y cantidad. Las propiedades modificadas para una composición deben
guardarse con esa composición, separadas del registro original del catálogo.

| Elemento | Configuraciones de referencia | Pestañas y particularidades |
| --- | --- | --- |
| Wall, Ceiling | Single, Double, Triple, Quad | Paneles intercalados con cámaras; Facing para Single; Leak |
| Floor | Single, Double, Triple | Floor Cover antes de Panel 1; representación de suelo; resultado original de INSUL: impacto |
| Roof | Single, Double | Rainfall; Facing para Single; resultado original: ruido de lluvia |
| Glazing | Single, Double, Triple, Quad | Cámara con gas; el modelo modal de INSUL admite Quad; el modelo energético llega a Triple |
| Porous | Absorbente independiente | Producto, espesor y resistividad al flujo; transmisión aérea del material poroso |

El límite Floor se confirma en [Floors][floors]; Roof, en [Roofs][roofs].
[Porous Material][porous] describe Facing para Single en aislamiento aéreo,
impacto y lluvia. La solicitud del usuario añade Facing a Single Glazing.

**Cuatro hojas necesitan tres cámaras interiores.** La secuencia físicamente
consistente es `Panel 1 → Frame 1 → Panel 2 → Frame 2 → Panel 3 → Frame 3 → Panel 4`.
Una cuarta cámara después de Panel 4 necesitaría definir una terminación o una
quinta hoja; no debe incorporarse como cámara interior sin esa definición.

La documentación pública contiene apartados desactualizados: [Tabs][tabs] aún
enumera tres configuraciones, mientras [Panels][panels] y [Glazing][glazing]
describen Quad. La página [Quad Panels][quad] solo indica que está en construcción.
Las capturas suministradas y las páginas específicas son la mejor evidencia de la
navegación actual, pero no documentan los algoritmos internos.

### Frame, Stud e infill

La guía [Item Details][items] define Stud como un registro de dimensiones. Un
Frame representa además una conexión acústica entre hojas: montante común,
montantes alternados, montaje independiente, etc. Importar ancho y profundidad de
un Stud no permite deducir la rigidez dinámica de la conexión o su transmisión
estructural.

El editor puede conservar el producto absorbente y su espesor aunque la cantidad
sea cero. En ese estado debe excluirlo tanto del modelo activo como de la
representación. La cantidad multiplicada por el espesor no puede exceder la
profundidad útil de cámara. Para un absorbente de fluido equivalente se necesita
resistividad explícita en Pa·s/m²; el nombre del material o su densidad por sí
solos no especifican ese parámetro.

## Leak: controles verificados y límite de evidencia

Se consultaron [Getting Started — Leaks][leaks-ui] y [Theory — Leaks][leaks-theory],
y se inspeccionaron sus imágenes enlazadas de propiedades:

- [Aperture properties][aperture-image].
- [Slit properties][slit-image].
- [Leak calculation settings][leak-settings-image].

| Control | Slit | Aperture |
| --- | --- | --- |
| Activación | Enabled | Enabled |
| Geometría | Altura, longitud y profundidad | Radio y profundidad |
| Posición | Middle, Edge | Middle, Edge, Corner |
| Método | Gomperts, Mechel | Gomperts, Mechel |
| Visualización de referencia | Plot Leak; Leak only | Plot Leak; Leak only |
| Mechel: sellado | Unsealed o Sealed | Unsealed o Sealed |
| Mechel: masas | Mass Side 1, Mass Side 2, **kg/m²** | Mass Side 1, Mass Side 2, **kg/m²** |
| Mechel: absorbente | Cavity is empty; Cavity Absorption | Cavity is empty; Cavity Absorption |

Las masas del sellado son **superficiales**, no masas totales en kg. Con ambas
masas a cero, la guía describe el caso sin sellado. Los controles de absorción y
sellado pertenecen a Mechel y deben quedar inactivos al elegir Gomperts. Corner
no es una posición documentada para Slit.

La guía recomienda Gomperts para aberturas vacías y describe Mechel como una
extensión que admite absorbente y masas de sellado. **No publica las ecuaciones
de ninguno de los dos métodos.** Identifica estas referencias primarias:

1. Gomperts, M. C. (1964). *The “sound insulation” of circular and slit-shaped
   apertures*. Acta Acustica united with Acustica, 14(1), 1–16.
2. Gomperts, M. C., y Kihlman, T. (1967). *The sound transmission loss of circular
   and slit-shaped apertures in walls*. Acta Acustica united with Acustica,
   18(3), 144–150.
3. Mechel, F. P. (1986). *The acoustic sealing of holes and slits in walls*.
   Journal of Sound and Vibration, 111(2), 297–336.
4. Griffin, D. (2018). *Accuracy of prediction methods for sound reduction of
   circular and slit-shaped apertures*. International Congress on Sound and
   Vibration 25.

Los textos completos anteriores **no se consultaron** en esta revisión. No es
defendible presentar una mezcla de áreas, una corrección de extremos inventada
o una matriz de conducto sin impedancias de radiación como “Gomperts” o “Mechel”.
Profundidad, posición, pérdidas termoviscosas y condiciones en las bocas afectan
la transmisión; disponer de controles no equivale a disponer de ese modelo.

Una combinación energética independiente sí puede explicitarse:

```text
S = ancho del elemento × altura del elemento
Sslit = altura de ranura × longitud de ranura
Saperture = π radio²
p = Sabertura / S
τconjunto(f) = (1 − p) τelemento(f) + p τabertura(f)
Rconjunto(f) = −10 log10[τconjunto(f)]
```

Todas las longitudes deben convertirse de mm a m antes de calcular áreas. Exigir
`0 ≤ p ≤ 1`. La hipótesis `τabertura = 1` corresponde a una **abertura ideal de
área libre**: no usa profundidad, posición, sellado ni absorbente, y no constituye
una solución Gomperts o Mechel. Cualquier opción no implementada debe impedir un
resultado atribuido a ese método, en vez de cambiar silenciosamente de modelo.

La misma guía advierte que los resultados cerca de resonancias pueden predecir
menos aislamiento que el observado. Su estimación de ±5 dB se refiere a las
rutinas de INSUL y no es una incertidumbre acreditada para Noiz.

## Facing y Porous

[Porous Material][porous] describe dos problemas: transmisión a través de un
absorbente independiente y transmisión a través de un panel con revestimiento
poroso. [Porous Facing][facing] explica la aproximación de fluido equivalente con
esqueleto inmóvil y confirma `Rayl/m = Pa·s/m²` para resistividad al flujo.

Las matrices de fluido equivalente ya descritas en
[la revisión V2](v2-reference-review.md) permiten implementar ambos casos con una
formulación propia. El orden del revestimiento y la placa debe ser explícito; no
debe tratarse el revestimiento poroso como una placa sólida de masa equivalente.
El resultado para un absorbente independiente es un índice de transmisión aérea,
no un coeficiente de absorción de una muestra sobre respaldo rígido.

La guía no identifica aquí una correlación concreta ni sus coeficientes. Elegir
Miki es una decisión documentada de Noiz y debe conservar su intervalo de ajuste,
los parámetros ambientales y las advertencias de extrapolación. Tampoco debe
inventarse una relación densidad–resistividad a partir de la existencia del
estimador de INSUL: la guía cita Beranek (1971), capítulo 8, pero no reproduce sus
ecuaciones.

## Acristalamientos y gases

[Glazing][glazing] distingue un modelo energético semiempírico de un modelo modal
finito. [Wave-based Glazing][glazing-wave] documenta:

- Gases de cámara: **aire, argón y kriptón**.
- Conexiones de borde: marco de aluminio, hojas aisladas, separador de unidad
  aislante, bastidor de madera y marco de laboratorio de madera.
- Vidrios laminados con espesor separado de Side A, Side B e interlámina.
- Promedio difuso y resultado de incidencia a un ángulo específico.
- Límite de integración angular configurable; 78° se menciona como una
  recomendación utilizada en algunas condiciones de laboratorio, no universal.

El gas afecta el número de onda y la impedancia de la cámara. Una extensión de
matrices de transferencia puede utilizar valores explícitos de densidad y
velocidad del sonido de cada gas, conservando el aire exterior y la componente
tangencial del número de onda. La guía no publica constantes termodinámicas ni
temperaturas de referencia; esos valores necesitan su propia procedencia.

Como aproximación termodinámica independiente, para un gas ideal de masa molar
`M` a temperatura `T` y presión `P`, `ρ = PM/(R T)` y
`c = sqrt(γ R T/M)`. Esto especifica un medio homogéneo ideal; no implementa el
modelo modal de INSUL, los sellos de borde o la transmisión por separadores.
El modelo de placa infinita tampoco debe denominarse “Wave-based INSUL” ni asumir
que el vidrio laminado tiene las propiedades de una placa monolítica.

La implementación V3 fija `T = 20 °C` y `P = 101325 Pa` de forma predeterminada,
con `R = 8.31446261815324 J/(mol·K)`. Sus masas molares convencionales son
0,02896546 kg/mol para aire, 0,039948 para argón, 0,083798 para kriptón y 0,131293
para xenón; usa `γ = 1,4` para aire y `5/3` para gases monoatómicos. Son valores
fijados del modelo ideal de Noiz, no constantes obtenidas del manual de INSUL ni
propiedades medidas de una cámara. Xenón es una ampliación propia; la guía
consultada solo enumera aire, argón y kriptón. No se modelan mezclas, humedad o
pérdidas termoviscosas del gas. Mantener la distinción entre el aire exterior
configurable y el gas de cada cámara permite reproducir el cálculo.

## Floor Cover: medición y predicción son datos distintos

[Floors][floors] y [Impact — Floor Covers][floor-theory] describen:

- Medido: diferencia por banda entre el suelo base y el mismo suelo con
  revestimiento. La procedencia puede ser laboratorio **o campo**.
- Selección por tipo de subestructura: ligera, CLT o pesada. No aplicar
  automáticamente la mejora de un suelo pesado a uno ligero.
- Predicho: opciones para corcho, caucho, recrecido, baldosa, madera y vinilo
  sobre suelo pesado, incluyendo propiedades del acabado y la base resiliente.
- La gráfica Floor Covering muestra la mejora por tercio de octava, separada del
  nivel total de impactos de la construcción.

Una curva importada no se convierte en ensayo verificado por estar bajo una
pestaña “Measured”. Deben conservarse el tipo de subestructura, la referencia de
ensayo y las observaciones del registro; un campo vacío o `XXX` no constituye
trazabilidad de laboratorio. Mostrar esa curva es distinto de predecir `Ln,w`.

Si se dispone de un espectro base de impacto compatible y una mejora medida
aplicable, la combinación por banda es `Ln,con = Ln,base − ΔL`. Este cálculo no
permite inferir el espectro base a partir del TL aéreo. Para una base resiliente,
la guía da la relación `E = s′ t`: rigidez dinámica **por unidad de área** en
N/m³ multiplicada por espesor en m produce un módulo en Pa. La implementación
de un modelo completo requiere además la teoría de Vér (1971), las hipótesis de
excitación de la máquina de impactos y validación experimental.

## Roof y lluvia

[Roofs][roofs] confirma solo Single y Double. Sus controles son:

| Laboratorio | Natural |
| --- | --- |
| Moderate, Intense, Heavy, Cloudburst | Tasa de precipitación en mm/h |
| Área de lluvia/tanque independiente del tamaño del panel | Lluvia sobre toda la superficie del panel |
| Referencia histórica ISO 140-18 | Distribución de gotas de Marshall–Palmer |

Los ajustes incluyen tipo de salida —potencia, intensidad o presión sonora— y,
para presión en recinto, volumen y tiempo de reverberación. [Rain Noise][rain]
describe la excitación por gotas paraboloidales de Petersson, integración de
impactos y radiación de la placa; **no publica el conjunto de ecuaciones y
parámetros necesario para reproducir el cálculo**.

Con lluvia natural, aumentar el área aumenta la potencia incidente total. Con
tanque fijo, la lluvia incidente no aumenta automáticamente con el área del
panel. Los niveles de intensidad y presión requieren conversiones distintas.
No puede obtenerse un nivel de lluvia en dBA restando TL a un número de lluvia
arbitrario. Tampoco se debe etiquetar un resultado aéreo como resultado Rainfall.

La lista de [References][references] reconoce ISO 140-18 como retirada y enumera
la familia ISO 10140 posterior. El nombre histórico de un control no constituye
una declaración de conformidad con una norma vigente.

## Resultados, visualización y evidencia de precisión

[Charts & Tables][charts] confirma la tabla resumen por octavas, la gráfica y
tabla por tercios de octava, las curvas de comparación y el gráfico específico
Floor Covering. Los valores por octavas deben agregarse en energía, no mediante
promedio aritmético de dB. Para incidencia con potencia uniforme por Hz:

```text
τoctava = Σ(Δfi · 10^(−Ri/10)) / ΣΔfi
Roctava = −10 log10(τoctava)
```

Esta es una convención de Noiz que debe indicarse; la página de INSUL no explica
cómo construye su tabla de octavas. Tampoco declara que su región gráfica
“Lab max” sea un límite universal de predicción: cita valores orientativos de
laboratorio de ISO 10140-5. No copiar esa banda sin un tratamiento normativo y de
procedencia propio.

Las capturas justifican una vista de composición, navegación por capas y vista
2D/3D. La implementación de Noiz puede dibujar geometría y materiales propios;
no necesita las texturas, logotipos, ejecutables o bibliotecas de Delphi de INSUL.
Skia4Delphi y SVGIconImageList son referencias de herramientas gráficas, no
fuentes de sus algoritmos acústicos. OpenSSL, PortAudio y OpenBLAS tampoco
aportan esos modelos por figurar en About.

Los intervalos del About aportado —`Rw ±3 dB`, `Ln,w ±5 dB`, lluvia `±5 dBA`— son
afirmaciones sobre INSUL. **No son márgenes de error de Noiz.** Un modelo propio
requiere verificación matemática, convergencia numérica y mediciones
independientes antes de atribuir precisión experimental.

## Catálogos XML v10 aportados

Los siete archivos nuevos declaran **Version 10.0, Release 8**. La importación
identificó estos registros:

| Familia | Registros |
| --- | ---: |
| Material | 1.575 |
| Profile | 281 |
| Glazing | 80 |
| Absorption | 523 |
| Floor cover | 669 |
| Core | 45 |
| Stud | 69 |
| **Total** | **3.242** |

La inspección del esquema confirma espesores en m, densidades en kg/m³ y módulos
en Pa. Hay 1.180 registros que cumplen los criterios de entrada del modelo de
placa isotrópica: 1.158 materiales y 22 vidrios. Cumplir esos criterios significa
que pueden convertirse en entradas del modelo; no acredita sus propiedades o su
precisión acústica.

Los registros de Stud aportan dimensiones, con categorías como MetalFrame y
TimberFrame; no aportan una función de acoplamiento mecánico. Los 669 registros
de Floor cover incluyen curvas `IsolationGain` en 28 bandas nominales entre 20
y 10.000 Hz: 616 para base pesada, 40 para ligera y 13 para CLT. Sus etiquetas
`Measured`/`Lab=True` no sustituyen la identificación de un informe de ensayo.
Material y Glazing no incluyen espectros de ensayo en estos XML.

Un nombre de Absorption contiene un carácter de control `U+0001`, no permitido
en XML 1.0. La importación conserva el hash de los bytes originales y registra
la reparación del nombre visible; no altera silenciosamente propiedades
físicas. El catálogo derivado permanece en el almacenamiento local del usuario,
separado del código fuente público y de los datos de ejemplo sintéticos.

## Qué permite implementar esta evidencia

| Función | Evidencia suficiente para una implementación propia | Lo que todavía requiere evidencia adicional |
| --- | --- | --- |
| Jerarquía de pestañas y listas | Guía, imágenes y solicitud del usuario | Pruebas de persistencia y navegación |
| Cuatro hojas / tres cámaras | Extensión física explícita de matrices de transferencia | Convergencia con resonancias estrechas; validación real |
| Facing / Porous | Fluido equivalente Miki con coeficientes y límites ya registrados | Propiedades verificadas de cada producto; validación real |
| Gas de cámara | Matriz fluida con densidad y velocidad documentadas | Modelo modal finito y conexiones de borde |
| Abertura ideal por área | Balance energético explícito | Gomperts/Mechel, radiación, pérdidas y sellado |
| Controles Gomperts/Mechel | Nombres, unidades y estados verificados | Artículos primarios completos y contrastes numéricos |
| Curva Floor Cover importada | Mostrar valores con procedencia y tipo de suelo | Validar ensayo, predecir suelo base y clasificación de impacto |
| Rainfall | Configuración documentada y persistible | Modelo de gotas, movilidad/radiación y validación de lluvia |
| Stud / Frame | Dimensiones y composición visual | Rigidez de conexión y transmisión estructural |

[tabs]: https://docs.insul.co.nz/v10/UsingINSUL/Tabs/
[panels]: https://docs.insul.co.nz/v10/GettingStarted/Panels/
[examples]: https://docs.insul.co.nz/v10/GettingStarted/Examples/
[floors]: https://docs.insul.co.nz/v10/GettingStarted/Floors/
[roofs]: https://docs.insul.co.nz/v10/GettingStarted/Roofs/
[glazing]: https://docs.insul.co.nz/v10/GettingStarted/Glazing/
[glazing-wave]: https://docs.insul.co.nz/v10/SoundInsulationTheory/Airborne-Glazing-WaveModel/
[porous]: https://docs.insul.co.nz/v10/GettingStarted/PorousMaterial/
[facing]: https://docs.insul.co.nz/v10/SoundInsulationTheory/Airborne-Porous-Facing/
[quad]: https://docs.insul.co.nz/v10/SoundInsulationTheory/Airborne-QuadPanels/
[items]: https://docs.insul.co.nz/v10/UsingINSUL/MaterialsEditor-Details/
[leaks-ui]: https://docs.insul.co.nz/v10/GettingStarted/Leaks/
[leaks-theory]: https://docs.insul.co.nz/v10/SoundInsulationTheory/Airborne-Leaks/
[aperture-image]: https://docs.insul.co.nz/v10/images/LeakApertureProperties.png
[slit-image]: https://docs.insul.co.nz/v10/images/LeakSlitProperties.png
[leak-settings-image]: https://docs.insul.co.nz/v10/images/SettingsLeaksTab.png
[floor-theory]: https://docs.insul.co.nz/v10/SoundInsulationTheory/Impact-FloorCovers/
[rain]: https://docs.insul.co.nz/v10/SoundInsulationTheory/Rain-Noise/
[references]: https://docs.insul.co.nz/v10/Resources/References/
[charts]: https://docs.insul.co.nz/v10/UsingINSUL/ChartsTables/
