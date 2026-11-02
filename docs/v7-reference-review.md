# V7: revisión de las fuentes de cálculo

Esta nota separa las ecuaciones efectivamente consultadas de las referencias que
todavía requieren comprobación. No establece un margen de error experimental
para Noiz ni equivalencia de resultados con Strutt o INSUL.

## Fuentes consultadas

- Bies, Hansen, Howard y Hansen, *Engineering Noise Control*, 6.ª edición,
  CRC Press, 2024. Capítulo 7, DOI `10.1201/9780367814908-7`, especialmente
  pp. 420–440. También §6.8.2, p. 383. El archivo aportado contiene texto;
  las ecuaciones 6.91 y la tabla 7.8 se verificaron además en la página renderizada.
  La página impresa 436 corresponde a la página 469 del PDF aportado.
- Vér, capítulo 11 de Vér y Beranek (eds.), *Noise and Vibration Control
  Engineering: Principles and Applications*, 2.ª edición, Wiley, 2006,
  pp. 439–445 (páginas 232–235 del PDF aportado). El archivo es escaneado;
  se consultaron imágenes de las páginas y OCR como auxiliar de localización.

Los archivos originales y las imágenes de páginas son material de consulta local;
no se incluyen en el repositorio.

## Decisiones de implementación en V7

La ruta Single utiliza la integración angular y energética de placa finita de
7.49–7.57, conservando el diagnóstico de extrapolación por debajo de `1.5*f11`.
No utiliza una mezcla ajustada entre los tramos de Davy y Sharp ni los une a
una asíntota de rigidez. El límite de espesor 7.76–7.77 se aplica al resultado
por centro de banda: para una banda que cruce su frecuencia de activación,
esa aproximación no equivale a aplicar el límite a cada frecuencia antes de
integrar la energía del tercio.

La ruta Double utiliza estimaciones analíticas por centro de tercio para los
regímenes de Hansen, junto con transmisión por conexiones puntuales o lineales.
Las discontinuidades entre tramos publicados no se ocultan con una corrección
de ajuste no documentada. La transición junto a la resonancia define el TL
total; separar vías en ese intervalo es una convención de presentación, no
una identificación física independiente de cada camino.

El modelo Single conserva un promedio numérico dentro de cada banda; el modelo
Double es una estimación analítica por centros. Sus etiquetas y referencias
deben mantener esa diferencia. La adición de montantes a Double tampoco valida
automáticamente cámaras triples o cuádruples con puentes estructurales.

## Single: tamaño finito, coincidencia y pérdidas

Hansen, ecuaciones 7.49–7.58, pp. 421–423, establece impedancia de placa,
transmisión oblicua y promedio de energía transmitida. La corrección del límite
angular 7.56 atribuida a Davy depende del área, perímetro y longitud de onda:

```text
cos²(theta_L) = min(0.9, lambda*P/(8*pi*A))
```

La ecuación de promedio 7.57 integra hasta `sin²(theta_L)` sin dividir por ese
límite. El alcance indicado es por encima de `1.5*f11`; limitar el ángulo no
equivale a resolver los modos de vibración de una placa en la región de rigidez.
El libro recomienda al menos 20 frecuencias por tercio y promedio aritmético
de coeficientes de transmisión, no promedio de TL en decibelios.

Sharp (§7.2.6.1, pp. 424–426) proporciona una aproximación de masa, transición
entre `fc/2` y `fc`, y coincidencia dependiente del amortiguamiento. Davy
(§7.2.6.2, pp. 426–427) incorpora el límite angular variable. La conclusión
del libro es que Davy suele representar mejor las bajas frecuencias y Sharp
la región de coincidencia. No demuestra que cualquier combinación entre ambos
sea mejor ni proporciona una mezcla universal válida para todos los materiales.

Las pérdidas de material y las de montaje deben distinguirse. El libro señala
que muchos valores tabulados de pérdida ya incluyen apoyos; añadir otra pérdida
de borde a esos valores puede contar dos veces el mismo mecanismo. Una corrección
de pérdidas no sustituye la transmisión explícita por montantes entre hojas.

### Corrección por espesor

Hansen §7.2.6.4, p. 428, ecuaciones 7.76–7.77, atribuye a Ljunggren (1991)
un límite de TL para espesores que dejan de ser pequeños respecto de la onda
de flexión. Para una placa homogénea:

```text
f_lim = sqrt(B/(h⁴*m))
TL_max = 20*log10(m*c_LI/(4*rho_air*c*h)) + 10*log10(eta) + 17
```

El límite se aplica para `f > f_lim`. `B` es la rigidez por unidad de ancho,
`h` el espesor, `m` la masa superficial y `c_LI` la velocidad longitudinal de
placa, `sqrt(E/[rho_material*(1-nu²)])`. Es una corrección de espesor de alta
frecuencia; no debe describirse como un solucionador completo de ondas de
cortante, placa Mindlin o materiales sándwich.

## Double: transmisión aérea y por conexiones

Hansen §7.2.8.2, pp. 434–438, presenta el modelo Davy y distingue explícitamente
las dos vías (ecuación 7.88):

```text
TL = -10*log10(tau_air + tau_stud)
```

Esto representa transmisión directa por el elemento, no flancos entre recintos.
No se suman los valores de TL de ambas vías.

### Resonancia y régimen aéreo

Las ecuaciones 7.89–7.92 incluyen las frecuencias de flexión entre montantes en
la resonancia masa–aire–masa modificada. La ecuación 7.91 utiliza la raíz superior
del sistema acoplado. El libro propone factores empíricos para determinados
montantes metálicos; no son constantes universales de cualquier perfil o aislador.

Las ecuaciones 7.100–7.106 describen la vía aérea. La corrección angular de la
doble hoja, ecuación 7.102, es distinta de la placa única:

```text
cos²(theta_L) = max(cos²(61°), min(0.9, lambda*P/(8*pi*A)))
```

El coeficiente medio de absorción de cámara de esas ecuaciones no es la pérdida
estructural de la placa ni la resistividad de un absorbente. El texto sugiere
`min(1, k*d)` para relleno fibroso de al menos 50 mm, y entre 0,1 y 0,15, limitado
por `k*d`, para cámara vacía. Son aproximaciones genéricas con ese alcance;
no prueban el comportamiento de cada producto del catálogo. La alternativa de
fluido equivalente Miki exige resistividad y espesor, y debe identificarse
separadamente para no sumar dos veces la absorción.

La tabla 7.10, p. 438, resume los regímenes y la interpolación en torno a la
resonancia modificada. Ese procedimiento no se extiende automáticamente a Triple
o Quad con uniones estructurales.

Su primer tramo empieza por encima de `1.5*f₁`. Para hojas con montantes
compartidos se comprueban los modos entre montantes de 7.89, no solamente el
modo del panel completo. Exigir el límite de ambas hojas —el mayor de los dos—
es una decisión conservadora de dominio. Las hojas independientes conservan
el diagnóstico del modo del panel completo. Asimismo, V7 rechaza combinaciones
con `f₀ ≥ 0.9*min(fc₁,fc₂)`, donde desaparece el orden de regímenes utilizado
por las expresiones aéreas de 7.100 y 7.103.

### Vía por montantes

Las ecuaciones 7.93 y 7.95 corresponden respectivamente a conexiones puntuales
y lineales. Exigen masa superficial, frecuencia crítica y pérdida de cada hoja,
eficiencias de radiación, densidad de conexiones o separación de montantes y
compliance del conjunto de unión.

- Para conexiones puntuales, la compliance tiene unidades de `m/N`.
- Para conexiones lineales, el análisis dimensional de 7.95 exige `m²/N`.
  No son parámetros intercambiables; el texto rotula explícitamente `m/N`
  junto a la expresión puntual.
- El texto recomienda el modelo puntual para madera. Para acero atornillado,
  compara la separación entre tornillos con un cuarto de la longitud de onda
  de flexión para elegir entre respuesta puntual y lineal.
- Los límites rígido y desacoplado corresponden a compliance nula y creciente,
  respectivamente, pero un dibujo o el nombre comercial de un clip no determina
  su compliance dinámica.

La referencia cruzada de este apartado remite a §6.8.2, ecuación 6.91, p. 383.
Sin embargo, esa sección declara que cambió respecto de ediciones anteriores:
ahora proporciona la eficiencia de una respuesta acústica difusa no resonante,
en lugar de una placa excitada por fuerza. Usar directamente esa eficiencia
forzada en la expresión de montantes produce coeficientes incompatibles con
casos ordinarios de placas ligeras. Existe por tanto una ambigüedad editorial
que requiere consultar la fuente primaria, no aplicar la referencia cruzada
de forma automática.

La eficiencia de radiación de ondas libres y excitación mecánica se describe
en §4.15, pp. 242–243, mediante las expresiones Maidanik/Leppington. El texto
de §11.3.1, junto a la ecuación 11.63, confirma expresamente esta distinción
entre excitación mecánica (§4.15) y respuesta acústica forzada (§6.8.2). El texto
indica que el perímetro usado incluye el contorno exterior más dos veces la
longitud de los montantes. Cualquier uso de esa formulación para la vía mecánica
debe identificarla explícitamente; no equivale a verificar todos los detalles
del modelo publicado por Davy ni de Strutt.

### Tabla de compliance de acero: ambigüedad que debe conservarse

Las ecuaciones 7.97 y 7.99 y la tabla 7.8, p. 436, contienen ajustes empíricos
atribuidos a Davy et al. (2019), originalmente obtenidos con perfiles C de 92 mm.
El símbolo `g` se describe como «gauge of steel», pero la página no define el
sistema de calibre ni proporciona una conversión desde milímetros. Los exponentes
positivos sugieren un número de calibre, pero esa observación no verifica las
unidades ni una norma US/MSG. Usar espesor en metros o milímetros como si fuera
ese parámetro no está justificado por el texto consultado.

Por ello, una implementación reproducible debe usar una compliance documentada
o resolver el significado de `g` contra la fuente primaria antes de certificar
el ajuste como una predicción por calibre. Una aproximación geométrica alternativa
debe identificarse como tal, no como el ajuste experimental de la tabla 7.8.

## Contraste con Vér/Beranek y Sewell

Vér, pp. 439–441, ecuaciones 11.105–11.108, separa ondas forzadas y libres,
disipación interna, transmisión a estructuras y radiación. Su estimación de
transmisión finita en la región controlada por masa se expresa mediante la
eficiencia de radiación de la placa finita. Esa región se encuentra bien por
encima de la primera resonancia; no es una solución general de rigidez.

Las pp. 443–445 y ecuaciones 11.109–11.114 describen una recursión de impedancia
y presión para capas múltiples, con conservación del número de onda tangencial.
Su extensión lateral es infinita. La representación de varias capas por sí sola
no incluye las uniones mecánicas ni demuestra precisión experimental.

No se ha identificado en las páginas revisadas una formulación completa atribuida
a Sewell con parámetros y dominio suficientes para implementarla bajo ese nombre.
La corrección finita de Davy y la aproximación de Vér no deben renombrarse Sewell.

## Referencias primarias identificadas, no validación del programa

La bibliografía de Hansen, pp. 828–829, identifica:

- Davy (2009), “The forced radiation efficiency of finite size flat panels that
  are excited by incident sound”, *JASA* 126, 694–702.
- Davy (2009), “Predicting the sound insulation of walls”, *Building Acoustics*
  16, 1–20.
- Davy (2010), “The improvement of a simple theoretical model for the prediction
  of the sound insulation of double leaf walls”, *JASA* 127, 841–849.
- Davy, Guigou-Carter y Villot (2012), “An empirical model for the equivalent
  translational compliance of steel studs”, *JASA* 131, 4615–4624.
- Davy, Fard, Dong y Loverde (2019), “Empirical corrections for predicting the
  sound insulation of double leaf cavity stud building elements with stiffer
  studs”, *JASA* 145, 703–713.

Identificar una referencia en la bibliografía no equivale a haber consultado sus
datos originales ni a validar el programa con ellos. Las comprobaciones de
ecuaciones, unidades y límites verifican la implementación; demostrar precisión
requiere casos ensayados con propiedades, geometría y uniones suficientemente
documentadas.
