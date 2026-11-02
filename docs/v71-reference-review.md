# V7.1: selección automática de marcos y alcance del modelo Double

La ruta automática de Double combina la vía aérea Davy/Hansen con la vía de
puentes rígidos de Sharp. Permite calcular una doble hoja ordinaria seleccionando
su marco y relleno, sin exigir al usuario una compliance dinámica. Es una
aproximación de ingeniería identificada como `davy-air-sharp-bridge-1`; no es una
reproducción de INSUL, una calibración nueva de Davy ni una demostración de
precisión de laboratorio. La ruta avanzada de V7 permanece diferenciada.

## Fuentes efectivamente consultadas

| Fuente | Localización relevante | Uso |
| --- | --- | --- |
| B. H. Sharp, “Prediction Methods for the Sound Transmission of Building Elements”, *Noise Control Engineering*, 11(2), septiembre–octubre de 1978, pp. 53–63 | Ecs. 4, 6–8, 17, 19–26; pp. 54–55 y 59–63 | Ley de masa de referencia, topología y asíntotas de puentes, ejemplos de diseño |
| L. Cremer, M. Heckl y B. A. T. Petersson, *Structure-Borne Sound: Structural Vibrations and Sound Radiation at Audio Frequencies*, 3.ª edición, Springer, 2005 | §§6.8.2, 7.7.2, 7.9.2–7.9.3 | Dominio de puentes, rigidez dinámica y separación de vías |
| D. A. Bies, C. H. Hansen, C. Q. Howard y K. L. Hansen, *Engineering Noise Control*, 6.ª edición, CRC Press, 2024 | §7.2.8.2 y tabla 7.10, pp. 434–438; tabla 7.12, p. 442 | Vía aérea Davy, interpolación de regímenes y propiedad de fibra de referencia |

El adjunto denominado `download` es el libro de Cremer, Heckl y Petersson de
2005; no es la edición de 1988 con Ungar que aparece en la captura de referencias.
En Sharp, la página 3 del PDF corresponde a la impresa 55. En Cremer, la página
524 del PDF corresponde a la impresa 514. En Hansen, la página 475 del PDF
corresponde a la impresa 442. Las ecuaciones relevantes de Sharp y la tabla de
resistividad de Hansen se comprobaron además en páginas renderizadas. La
extracción de texto de Cremer contiene una codificación defectuosa; se utilizó
texto decodificado para localizar secciones y la imagen para comprobar fórmulas.
Los PDF, imágenes y extracciones de consulta no se redistribuyen con el código.

La revisión de tamaño finito, pérdidas, límite por espesor y ambigüedad del
calibre de acero de V7 sigue en [v7-reference-review.md](v7-reference-review.md).

## Qué representa seleccionar un marco

Sharp, p. 59, considera los montantes ordinarios de madera **o de metal** como
conexiones lineales. La sujeción mediante tornillos sobre una pestaña continua
no basta para tratar el contacto como puntual. La figura 9 representa un apoyo
puntual real sobre una de las hojas; su topología difiere de una hoja apoyada a
lo largo de todo el montante.

La selección automática de un marco común de madera o acero utiliza esa
aproximación de contacto rígido lineal. No deduce una mejora por flexibilidad
del nombre del producto, por su categoría comercial ni por el espesor de chapa.
Hansen, p. 434, §7.2.8.2, señala expresamente que la rigidez infinita es una
hipótesis aceptable para montantes de madera, pero no para los perfiles metálicos
de pared delgada habituales: esa diferencia motiva el modelo de compliance de
Davy. Por tanto, habilitar el cálculo automático de acero con el límite rígido
no demuestra que su precisión para perfiles flexibles haya quedado resuelta.
La ventaja acústica específica de perfiles flexibles, canales resilientes,
clips, resortes o elastómeros requiere datos dinámicos adicionales. Modelar
su geometría o dibujar un resorte no proporciona esos datos.

Los bastidores realmente independientes pueden excluir el puente común. Los
montantes alternados con soleras compartidas no equivalen automáticamente a
bastidores completamente independientes. El modo puntual identifica qué hoja
se apoya en puntos; el caso de puntos en ambas hojas usa las impedancias
puntuales de Sharp. Estas hipótesis deben conservarse en los resultados y
proyectos, aunque no requieran una ventana de parámetros complejos.

## Ecuaciones de puente utilizadas

Todas las masas siguientes son superficiales, en kg/m²; las frecuencias están
en Hz y las separaciones en metros. Los logaritmos son decimales. Para
`M = m1 + m2`, la ley de masa de referencia de Sharp, ecuación 4, es:

```text
TL_M(f) = 20 log10(M f) - 48
```

La respuesta dominada por el puente, ecuación 19, es
`TL_bridge = TL_M + ΔTL_M`. El término lineal de diseño de la ecuación 24 es:

```text
ΔTL_M = 10 log10(b fc) + 20 log10(m_other / M) - 18
```

Aquí `b` es la separación entre montantes, `fc` es la **mayor** frecuencia crítica
de las dos hojas y `m_other` corresponde a la **otra** hoja. La pareja se elige
por esas propiedades, no por el orden de los paneles. Si ambas frecuencias
críticas coinciden pero las masas no, la implementación toma la menor masa para
`m_other`: es una decisión conservadora y recíproca de la implementación, no un
ajuste experimental publicado.

Para apoyos puntuales en una hoja y lineales en la otra, la ecuación 23 es:

```text
ΔTL_M = 20 log10(e fc) + 20 log10(m_other / M) - 45
```

En este caso `fc` es la frecuencia crítica de la hoja apoyada en puntos y
`m_other` la masa de la otra hoja. `e` es el paso de una malla cuadrada regular,
no el ancho del montante. Representar una malla rectangular por
`e = sqrt(paso_horizontal * paso_vertical)` conserva la densidad de puntos,
pero no resuelve su anisotropía.

Para puntos en ambas hojas, las ecuaciones 17, 20 y 22 dan una forma recíproca:

```text
fc_equivalent = (m1 fc2 + m2 fc1) / M
ΔTL_M = 20 log10(e fc_equivalent) - 45
```

Esto sigue suponiendo puentes rígidos y sin masa. No es un modelo de
transmisibilidad de un resorte ni del comportamiento viscoelástico de un aislador.

### No confundir la aproximación de diseño con la fórmula de impedancia

Sharp presenta las ecuaciones 23 y 24 como aproximaciones prácticas de las
ecuaciones 20–22. No son identidades algebraicas. En la formulación completa:

```text
K = 20 log10[m1 (Z1 + Z2) / (Z1 (m1 + m2))]
```

Para hojas idénticas, `K = 0`, mientras que la aproximación de diseño usa
`20 log10(1/2) = -6.02 dB`. El programa debe identificar la ecuación empleada;
no se puede alternar entre ambas bajo la misma etiqueta de modelo. La elección
lineal automática es la ecuación 24, que Sharp también utiliza en su figura 12
y en el procedimiento de diseño.

## Combinación con la vía aérea y resonancia

La combinación de caminos se realiza en energía transmitida:

```text
tau_total = tau_air + tau_bridge
TL_total = -10 log10(tau_total)
```

Esto corresponde al principio de las ecuaciones 7–8 de Sharp y 7.88 de Hansen.
No se suman TL en decibelios ni se elige simplemente la menor de las dos curvas.
La respuesta aérea conserva el tratamiento Davy/Hansen de tamaño finito,
absorción de cámara y coincidencia utilizado en V7. La vía estructural utiliza
la asíntota de Sharp de 6 dB por octava; su continuación en la región de
coincidencia es una aproximación, no un solucionador completo de vibración de
las hojas. Esta combinación no demuestra un límite inferior universal del TL.

Por debajo de la transición domina la respuesta de masa total; no se suma
otra vez una vía de puente que representaría la misma respuesta acoplada.
Entre `2 f0 / 3` y `f0`, la implementación interpola TL frente a `log(f)` usando
el extremo del modelo combinado. La convención de interpolación procede de
Hansen, tabla 7.10; el extremo combinado Davy–Sharp es una decisión de este
modelo, no una curva publicada como tal. El reparto de energía entre las dos
vías dentro de esa transición es contable, no una identificación experimental.

La frecuencia `f0` utilizada es la del sistema físico de dos masas y resorte
de aire:

```text
f0 = sqrt(rho_air c² (1/m1 + 1/m2) / d) / (2 pi)
```

Es importante distinguirla de la transición impresa por Sharp, p. 55:

```text
f0_Sharp = 113 / sqrt(me d)
me = 2 m1 m2 / (m1 + m2)
fl_Sharp = 55 / d
```

La constante `113` está efectivamente en la fuente y concuerda con el ejemplo
de diseño de p. 63 (`m1 = m2 = 14.5 kg/m²`, `d = 0.17 m`, aproximadamente
72 Hz). No es una transcripción errónea de la constante de la resonancia física.
La ruta automática no implementa literalmente la ecuación 6 de Sharp ni usa
su transición como si fuera la frecuencia del resorte de aire.

## Relleno absorbente sin pedir resistividad al usuario

Una resistividad expresamente proporcionada por el catálogo o el proyecto
prevalece sobre cualquier referencia genérica. Cuando falta para un relleno
fibroso compatible, la aplicación puede asumir **20 000 Pa·s/m²**, identificados
como propiedad de fibra de referencia, y aplicar Miki con el espesor real
seleccionado. La tabla 7.12 de Hansen, p. 442, ofrece estas propiedades para
ejemplos de fibra de vidrio o lana de roca:

| Resistividad de flujo [Pa·s/m²] | Densidad aparente [kg/m³] | Espesor del ejemplo [m] |
| ---: | ---: | ---: |
| 4 000 | 20 | 0.05 |
| 20 000 | 48 | 0.05 |
| 20 000 | 48 | 0.10 |
| 55 000 | 100 | 0.05 |

La tabla publica **TL calculados**, no mediciones de productos comerciales.
Elegir su fibra de referencia de 20 000 Pa·s/m² no asigna una medición al producto,
no establece que toda lana tenga esa resistividad y no autoriza interpolarla
únicamente a partir de su densidad. El origen supuesto debe permanecer visible
en los diagnósticos y el informe. Un cambio de espesor de 40 a 50 mm se evalúa
con el mismo modelo; no activa un salto arbitrario de algoritmo al cruzar 50 mm.

La aproximación de absorción de Hansen para rellenos de al menos 50 mm,
comentada en la revisión V7, es otra aproximación. No debe confundirse con el
uso de Miki con resistividad explícita y espesor real, ni sumarse a él como una
segunda bonificación por relleno.

El cálculo Miki empleado obtiene absorción difusa de una capa con respaldo
rígido para aproximar la absorción media de la cámara. Esa sustitución es una
decisión de ingeniería del programa: no equivale a un ensayo de la cámara ni
es una ecuación publicada por Davy. También debe conservar su diagnóstico de
extrapolación cuando la relación entre frecuencia y resistividad quede fuera
del intervalo empleado para el modelo empírico.

La ruta automática conserva el nivel de pérdidas de la cámara vacía mediante
`alpha = min(k d, max(0.1, alpha_Miki))`. Así, introducir una capa muy delgada
no sustituye la absorción de fondo por una estimación menor. Es una envolvente
de ingeniería, no una corrección publicada por Davy ni una suma de mecanismos
independientes demostrada. El valor de fondo procede del extremo inferior del
intervalo de Hansen, p. 437; su conservación al añadir el relleno es una decisión
de V7.1. La ruta avanzada anterior no cambia por defecto.

Sharp, pp. 56–58, compara cámaras con diferentes fibras y distribuciones. La
figura 5 estudia capas de 51 y 102 mm de tablero de fibra de vidrio de
48 kg/m³ en una cámara de 160 mm; la figura 6 compara tablero de 51 mm con
mantas de 89 mm y observa diferencias a alta frecuencia. Esas observaciones
no justifican una bonificación fija de TL para toda lana ni un espesor mínimo
universal de 40 o 50 mm.

## Qué aporta Cremer y qué no permite deducir

En §6.8.2, pp. 427–430, el puente puntual se representa por una barra corta
que transmite ondas longitudinales. Su límite de rigidez incluye
`s = E S / d`, además de la masa de la barra. Esta geometría no equivale a
la flexión de las alas y el alma de un perfil C. Introducir únicamente ancho y
fondo del montante en esa expresión no determina su compliance real.

El §7.7.2, pp. 512–514, trata un cerramiento masivo con revestimiento y
conexiones; las ecuaciones 7.76e–f distinguen contactos puntuales y lineales y
dependen de las velocidades transmitidas. No proporcionan una constante
universal para clips o aisladores. El §7.9.2, pp. 528–531, desarrolla doble
hoja bajo hipótesis de acoplamiento débil y pérdidas; el §7.9.3, desde p. 531,
trata conexiones rígidas con restricciones sobre la separación respecto de
la longitud de onda de flexión. Ninguna de esas secciones elimina la necesidad
de caracterizar dinámicamente un soporte resiliente comercial.

La ambigüedad del parámetro de calibre de la tabla 7.8 de Hansen descrita en
la revisión V7 no queda resuelta por estos adjuntos. V7.1 evita depender de esa
conversión desconocida en su ruta automática; no afirma haberla verificado.

## Verificación numérica y límites de validación

Los ejemplos de diseño de Sharp, pp. 62–63, ofrecen comprobaciones independientes
de la transcripción de las ecuaciones. Para un objetivo de 58 dB a 1000 Hz,
`fc = 4000 Hz` y paso de `0.61 m`, las ecuaciones 25–26 dan aproximadamente
29 kg/m² de masa total con una hoja apoyada en puntos y 64 kg/m² con conexiones
lineales. Son comprobaciones de fórmula, no validación de la combinación aérea
Davy–Sharp en todas las bandas.

También son comprobables la reciprocidad al intercambiar hojas y apoyos, el
incremento de aproximadamente 3.01 dB de la asíntota lineal al duplicar el paso,
el incremento de 6.02 dB de la puntual al duplicar el paso de una malla cuadrada,
y la suma energética de vías. Estas relaciones no sustituyen ensayos de un muro.

Las figuras 12 y 13 contienen comparaciones experimentales de configuraciones
concretas; la figura 12 usa placas de yeso de 15.9 y 9.5 mm, montantes de madera
a 0.61 m y fibra en cámara. El artículo no proporciona todos los datos de entrada
y una tabla digital por banda para convertir esa figura sin ambigüedad en un
caso de validación del programa. No se han inventado muestras a partir de las
capturas de INSUL ni se atribuye al software el error experimental del artículo.

La mejora verificable de esta versión es una ruta Double automática, trazable y
con suma de transmisión por marco y cámara. Establecer un margen de precisión
requiere todavía conjuntos de ensayo con materiales, dimensiones, fijaciones,
resistividad y resultados por banda documentados. La implementación no amplía
por sí sola el dominio validado de Triple o Quad con puentes estructurales.
