# Revisión de las fuentes para V6

Esta nota registra las fórmulas y los límites identificados durante la revisión
de los tres libros aportados. Una referencia bibliográfica, una verificación
matemática y una comparación experimental son evidencias distintas. Ninguna de
las fórmulas siguientes acredita una precisión de ±3 dB para Noiz Transmission.

Los números de página principales corresponden a la **paginación impresa**. Las
páginas PDF indicadas entre paréntesis identifican los archivos concretos
aportados; no necesariamente coinciden con otras digitalizaciones. Los libros y
sus extracciones no se distribuyen con el código.

## Placa rectangular: dimensiones y primera resonancia

Bies, Hansen, Howard y Hansen, *Engineering Noise Control*, 6.ª edición,
copyright 2024, §7.2.6, p. 421 (PDF 454), ecuación 7.45:

```text
B = E h³ / [12(1 − ν²)]                              [N m]
m = ρ_material h                                    [kg/m²]
f_mn = (π/2) √(B/m) [(m_index/a)² + (n_index/b)²]     [Hz]
```

Los índices modales son enteros positivos; para el primer modo ambos son 1.
`a`, `b` y `h` son longitudes en metros, `E` se expresa en Pa y `ν` es
adimensional. La fórmula corresponde a una placa delgada isotrópica rectangular
**simplemente apoyada en los cuatro bordes**. No identifica por sí misma las
condiciones reales de una placa atornillada a montantes.

Barron, *Industrial Noise Control and Acoustics*, copyright 2003,
§4.8.2, pp. 111–112, ecuaciones 4-155–4-157, da la expresión equivalente mediante
la velocidad longitudinal del material. Advierte que las pérdidas en los bordes
afectan mucho al aislamiento cerca de las primeras resonancias.

Calcular `f11` permite advertir dónde falla una aproximación de placa infinita;
no equivale a haber calculado la respuesta modal ni añade una resonancia al
espectro calculado.

## Tamaño finito: aproximación angular de Davy

Bies et al., pp. 422–423 (PDF 455–456), ecuaciones 7.49, 7.51 y 7.56–7.57:

```text
Z(θ) = j 2π f m [1 − (f/fc)² (1 + jη) sin⁴θ]
τ(θ) = |1 + Z(θ) cosθ / (2ρ_air c)|⁻²
λ = c/f;  A = ab;  P = 2(a+b)
cos²θL = min(0.9, λ P / (8π A))
τF = ∫[0, sin²θL] τ(θ) d(sin²θ)
R = −10 log10(τF)
```

El signo de la parte disipativa de `Z` depende de la convención temporal; su
implementación debe ser consistente y pasiva. El límite y la integral se
comprobaron visualmente en la página original. La ecuación 7.57 **no divide**
la integral por `sin²θL`. Normalizar el intervalo produciría otra aproximación.

El libro exige `f > 1.5 f11`. Para obtener un tercio de octava recomienda
promediar aritméticamente los coeficientes `τF` calculados en al menos 20
frecuencias de la banda y después convertir a dB. No recomienda promediar dB.
La corrección cambia con área, perímetro y frecuencia; no modela explícitamente
los modos propios ni los apoyos. Fuera de su dominio no debe presentarse como
una solución de la región controlada por rigidez.

La atribución del libro es Davy (2009b), con modificación de Davy (2010). La
ecuación anterior no es una reproducción de la solución de Sewell.

## Amortiguamiento de borde y pérdida total

Bies et al., p. 714 (PDF 747), ecuaciones 11.75–11.76:

```text
η_total = η_material + η_junction + η_radiation
η_radiation = ρ_air c σ / (ω m)       [un lado que radia; adimensional]
```

Las pérdidas de material, unión y radiación son mecanismos diferentes. La
contribución de la unión depende de su configuración y debe medirse, proceder
de una referencia aplicable o declararse como entrada de sensibilidad. La
revisión no justifica una constante universal calculada solamente a partir de
densidad, nombre del fabricante o tipo de material.

Las pp. 424–427 y 714 advierten que muchas pérdidas tabuladas para paneles
instalados ya incluyen soportes y radiación. Por ello no se debe añadir de nuevo
una contribución de borde a un valor medido que ya la contiene. Tampoco debe
añadirse por segunda vez radiación si el modelo ya carga la placa con el fluido.

Vér, capítulo 11 de Vér y Beranek (eds.), *Noise and Vibration Control
Engineering: Principles and Applications*, 2.ª edición, 2005, p. 402
(PDF 214), ecuaciones 11.29–11.31, expone el balance equivalente: potencia
disipada internamente, transmitida a estructuras conectadas y radiada al fluido.

## Región controlada por rigidez: límites de las aproximaciones

Bies et al., p. 426 (PDF 459), ecuaciones 7.66–7.68, presenta una adaptación de
Fahy y Gardonio para un modo equivalente de una placa apoyada. Define

```text
s = π⁴ B (1/a² + 1/b²)²                       [N/m³]
R ≈ 20 log10[s / (4π f ρ_air c)]               para f < 0.5 f11
```

En la zona `0.5 f11` a `1.5 f11`, su expresión de resonancia requiere que
`η` sea mucho mayor que `ρ_air c/(2π f m)`; para el límite opuesto propone
`R = 0`. No es una transición modal completa ni una interpolación suave
validada para cualquier amortiguamiento.

Hay una inconsistencia aparente en la ecuación 7.65: imprime `f0 = √(s/m)`
en Hz, mientras que su definición de rigidez 7.66 y la ecuación modal 7.45
requieren `f0 = √(s/m)/(2π)`. No debe copiarse literalmente 7.65 para convertir
una frecuencia angular en Hz.

Vér, pp. 422–424 (PDF 224–225), estudia por separado el caso acústicamente
pequeño, `L ≪ λ`, y distingue `f ≪ f11`, `f ≈ f11` y `f ≫ f11`.
La compliance de volumen es `Cv = ΔV/p` [m⁵/N]. Para una placa homogénea,
isotrópica y presión uniforme, la ecuación 12.6, p. 525 (PDF 275), proporciona

```text
Cv = 10⁻³ A³ F(a/b) / B
```

`F` se obtiene de la figura 12.4, p. 526 (PDF 276), con curvas distintas para
bordes apoyados y empotrados. La ecuación no proporciona por sí sola `F` como
función cerrada. La respuesta acústica de esa placa pequeña no debe aplicarse
a una partición arbitraria, ni sumarse como una corrección en dB a todas las
bandas de un sistema multicapa.

Barron, p. 111, ecuación 4-152, proporciona una compliance específica cerrada
para la aproximación de placa rectangular. Es útil como referencia de
verificación de la región de rigidez; no sustituye un cálculo de acoplamiento
modal placa–cavidad–placa.

## Radiación finita en Vér/Beranek y sistemas con varias hojas

Vér, pp. 439–441 (PDF 232–233), ecuaciones 11.105–11.108, distingue ondas
forzadas y libres, y presenta la estimación

```text
R_E ≈ R_normal − 3 − 10 log10(σ_forzada)
```

con eficiencia de radiación finita de su tabla 11.8. La atribución es
Sato (1973) y Rindel (1975), no Sewell. La p. 441 exige una respuesta controlada
por masa, bien por encima de la primera resonancia. No convierte esta fórmula
en solución del dominio de rigidez.

Las pp. 443–445 (PDF 234–235), ecuaciones 11.109–11.114 y el procedimiento
numerado, fundamentan la recursión de impedancia y presión para `N` capas:
conservación de la componente tangencial del número de onda, continuidad de
presión/velocidad, impedancia de placa, capas de aire o absorbente y promedio
angular de la transmisión. El modelo tiene extensión lateral infinita.

Por tanto, usar una cadena de transferencia para Single/Double/Triple/Quad es
una generalización del número de capas. Añadir a esa cadena el límite angular
de la placa única es una **extensión aproximada del programa**, no una
validación publicada específica para triple o cuádruple hoja.

Además, Bies et al. §7.2.8.2, pp. 434–438, presenta un modelo Davy específico
de doble hoja que incluye transmisión aérea y por montantes, compliance de
las conexiones y absorción de la cavidad. Su ecuación 7.102, p. 437 (PDF 470),
limita `cos²θL` entre `cos²(61°)` y `0.9`, a diferencia de la ecuación 7.56
de la placa única. Aplicar 7.56 a una cadena de transferencia no reproduce ese
modelo completo de doble hoja.

## Sewell y referencias pendientes

No se identificó una formulación completa atribuida a Sewell en los capítulos
revisados de los tres archivos aportados ni en la lista de referencias de la
guía INSUL 10 consultada. Esto no afirma que el modelo no exista. Significa
que estas fuentes no justifican etiquetar una implementación como «Sewell».
Para incorporarlo con ese nombre faltan la fuente primaria, sus ecuaciones y
condiciones de aplicación verificadas, más casos independientes de contraste.

Referencias identificadas en la bibliografía de Bies et al., pp. 828–829,
para contraste posterior; los artículos completos no se consultaron en esta
revisión:

- Davy (2009a), “The forced radiation efficiency of finite size flat panels that
  are excited by incident sound”, *JASA* 126, 694–702.
- Davy (2009b), “Predicting the sound insulation of walls”, *Building Acoustics*
  16, 1–20.
- Davy (2010), “The improvement of a simple theoretical model for the prediction
  of the sound insulation of double leaf walls”, *JASA* 127, 841–849.
- Davy, Guigou-Carter y Villot (2012), “An empirical model for the equivalent
  translational compliance of steel studs”, *JASA* 131, 4615–4624.
- Davy, Fard, Dong y Loverde (2019), “Empirical corrections for predicting the
  sound insulation of double leaf cavity stud building elements with stiffer
  studs”, *JASA* 145, 703–713.

La guía [INSUL 10: paneles simples](https://docs.insul.co.nz/v10/SoundInsulationTheory/Airborne-SinglePanels-Overview/)
y sus [referencias](https://docs.insul.co.nz/v10/Resources/References/), consultadas
el 23-10-2026, describen mecanismos, ejemplos y bibliografía; no proporcionan una
especificación abierta completa de su motor. Sus márgenes de error y ajustes
empíricos no se transfieren a Noiz Transmission.
