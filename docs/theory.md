# Modelo físico y clasificación

La versión 2 implementa un modelo propio de transmisión aérea por placas
isótropas infinitas y cámaras, identificado como `transfer-matrix-plate-1`.
La ruta histórica v1, `mass-law-1`, permanece disponible. Ninguna ruta reproduce
los algoritmos internos de INSUL ni hereda su precisión declarada.

## Magnitudes y convenciones

| Símbolo | Magnitud | Unidad |
| --- | --- | --- |
| f, ω = 2πf | Frecuencia y frecuencia angular | Hz, rad/s |
| ρ, h, m' = ρh | Densidad, espesor y masa superficial de placa | kg/m³, m, kg/m² |
| ρ0, c0, Z0 = ρ0c0 | Densidad, velocidad e impedancia característica del aire | kg/m³, m/s, Pa·s/m |
| E, ν, η | Young, Poisson y factor de pérdidas estructural | Pa, adimensional, adimensional |
| D | Rigidez de flexión | N·m |
| σ | Resistividad estática al flujo | Pa·s/m² = Rayl/m |
| θ | Ángulo de incidencia respecto a la normal | rad en las ecuaciones |

El aire predeterminado usa `ρ0 = 1.21 kg/m³` y `c0 = 343 m/s`. Son condiciones
explícitas de referencia, no una corrección meteorológica. Se exige estabilidad
elástica `E > 0`, `−1 < ν < 0.5` y `η ≥ 0`.

Se adopta dependencia temporal `exp(jωt)` y onda progresiva `exp(−jkz)`.
Un número de onda de medio pasivo tiene parte imaginaria no positiva. Todas las
conversiones de mm/GPa a m/Pa se realizan antes del cálculo físico.

## V2: placa infinita con masa, flexión y pérdidas

Para una placa delgada homogénea:

```text
m' = ρh
D = E h³ / [12(1 − ν²)]
kt = (ω/c0) sinθ
Zp = jωm' − jD(1 + jη) kt⁴/ω
P = [[1, Zp], [0, 1]]
```

`Zp` relaciona salto de presión con velocidad normal de placa. El signo disipativo
puede comprobarse mediante `Re(Zp) = Dηkt⁴/ω ≥ 0`. A incidencia normal `kt = 0`
y la expresión recupera la masa flexible. A incidencia oblicua la rigidez puede
compensar la inercia, produciendo coincidencia; las pérdidas modifican su respuesta.

La frecuencia crítica ideal, en el límite de incidencia rasante, es:

```text
fc = c0²/(2π) × sqrt(m'/D)
```

La curva v2 incorpora la flexión. Esta frecuencia sigue siendo un diagnóstico de
placa ideal: no es un modo propio de una placa finita ni un dato experimental.
El modelo no incorpora cizalladura en placas gruesas, condiciones de borde,
radiación finita, dimensiones modales o amortiguamiento de fijaciones.

### Varias capas dentro de una hoja

Una hoja admite hasta seis capas, cada una con cantidad `n_i`. Se supone que
comparten desplazamiento transversal y permiten deslizamiento relativo en el plano:

```text
m'panel = sum(n_i ρ_i h_i)
Dpanel = sum(n_i D_i)
ηpanel = sum(n_i D_i η_i) / Dpanel
```

No se usa el cubo de la suma de espesores ni se añaden términos de eje paralelo.
Dos capas iguales conservan la relación `m'/D` y, por tanto, `fc`; una placa
monolítica del doble de espesor no es equivalente. No es un modelo de unión
adhesiva continua, núcleo sándwich o lámina viscoelástica de vidrio laminado.

## V2: cámaras de aire y relleno poroso

Se admiten una a tres hojas, con exactamente una cámara entre hojas consecutivas.
El modelo incluye el camino aéreo; no introduce puentes estructurales de montantes.

Para un fluido con número de onda `k`, impedancia característica `Zc` y espesor `d`:

```text
kz = sqrt(k² − kt²), rama pasiva
Zn = Zc k/kz
F = [[cos(kz d), jZn sin(kz d)],
     [j sin(kz d)/Zn, cos(kz d)]]
```

En aire `k = ω/c0`, `Zc = ρ0c0`. Se conserva la componente tangencial `kt` en
cada interfaz. Una cámara parcialmente rellena se representa como aire, absorbente
y aire, repartiendo por igual el espesor de aire restante a ambos lados del relleno.
No se modela contacto mecánico del absorbente con las hojas.

### Fluido equivalente de Miki

Se requiere espesor de absorbente positivo no mayor que la cámara y resistividad
`σ` positiva explícita. El esqueleto del absorbente se supone inmóvil. La función
implementada, contrastada con Phonometry 3.3.0, usa:

```text
Y = f/σ                         [f en Hz; σ en Pa·s/m²]
Zc = ρ0c0 [1 + 0.070 Y^−0.632 − j0.107 Y^−0.632]
k  = (ω/c0) [1 + 0.109 Y^−0.618 − j0.160 Y^−0.618]
```

Se conserva el coeficiente `0.070` de la versión de Phonometry usada; algunas
fuentes secundarias publican `0.0699`. La comparación requiere igualar también las
condiciones del aire. El intervalo del ajuste es `0.01 < f/σ < 1`. Si las bandas
se extienden fuera de ese intervalo, la predicción advierte extrapolación e
incertidumbre no cuantificada. Estabilidad numérica fuera del intervalo no
establece exactitud física.

`Damping` del XML de absorbentes no se interpreta como `σ`; la documentación
consultada no confirma tal correspondencia. La densidad por sí sola tampoco se
convierte en resistividad. Referencias y estado de lectura:
[v2-reference-review.md](v2-reference-review.md).

## V2: transmisión y promedio energético

Multiplicar matrices en orden desde el lado emisor produce `T = P1 F1 P2 …`.
Con el mismo aire a ambos lados y `Za = ρ0c0/cosθ`:

```text
t = 2 / (T11 + T12/Za + T21 Za + T22)
τ(f,θ) = |t|²
```

Para incidencia normal se evalúa `θ = 0`. Para campo difuso truncado:

```text
τdifusa(f) = integral₀^θmax[τ(f,θ) sinθ cosθ dθ]
            / integral₀^θmax[sinθ cosθ dθ]
```

La normalización corresponde al mismo límite angular. El predeterminado `78°`
es una elección de modelado guardada en el proyecto; no es universal ni calibra
el modelo frente a un laboratorio particular. La API admite hasta 90°.

### Bandas de tercio de octava

La salida usa etiquetas nominales de 50 a 5000 Hz, pero la integración v2 emplea
centros exactos base 10 y límites exactos:

```text
fc,banda = 1000 × 10^(n/10), n = −13,…,7
finferior = fc,banda × 10^(−1/20)
fsuperior = fc,banda × 10^(1/20)
τbanda = integral_finferior^fsuperior[τ(f) df] / (fsuperior − finferior)
TLbanda = −10 log10(τbanda)
```

Se supone **potencia incidente uniforme por Hz** dentro de cada banda. Otro
espectro incidente necesita otro peso. No se promedian niveles dB ni se usa el
valor en el centro nominal como sustituto de la integral v2.

La integración localiza primero las resonancias mediante raíces de los términos
complejos de reflexión y transmisión y subdivide su entorno según su anchura.
La incidencia normal integra sobre frecuencia; la difusa resuelve las resonancias
angulares y después integra su promedio sobre frecuencia, incluyendo cambios en
los límites angulares y frecuencias críticas. El acuerdo entre dos mallas globales
sin localizar resonancias no se acepta como evidencia suficiente de convergencia:
ambas podrían omitir el mismo pico estrecho.
La tolerancia numérica predeterminada es **0,05 dB**, no una incertidumbre de
predicción. Las resonancias estrechas requieren resolución adicional; si no se
cumple la convergencia o la pasividad se informa un error. No se devuelven curvas
fabricadas mediante recorte de resultados físicamente imposibles. Los cálculos
admiten cancelación cooperativa para cerrar el editor durante la integración.

## Abertura ideal y diagnósticos

Para una fracción abierta `p = leak_percentage/100` se admite una combinación
energética ideal de áreas, con transmisión unitaria por la abertura:

```text
τtotal = (1 − p) τplacas + p
TLtotal = −10 log10(τtotal)
```

A altas prestaciones el límite es `−10 log10(p)` dB cuando `p > 0`. No es un
modelo de rendijas o agujeros con difracción, profundidad, sellos o resonancias.
No reproduce las rutinas de fugas de INSUL.

La masa superficial informada suma solo placas sólidas, sin masa de estructura
ni de absorbente. Ancho y alto son metadatos geométricos: no modifican la curva
del modelo infinito. El espesor total incluye placas y cámaras.

Para dos hojas, el diagnóstico concentrado de aire sin pérdidas es:

```text
f0 = sqrt[(ρ0c0²/d)(1/m'1 + 1/m'2)] / (2π)
```

Para tres hojas se usa la cadena acoplada de masas y muelles de aire: cada cámara
aporta rigidez `s_i = ρ0c0²/d_i` a las dos masas vecinas. Las raíces de los
autovalores no nulos de `M^−1/2 K M^−1/2`, divididas por `2π`, dan las dos
frecuencias diagnósticas. Se excluye el modo de traslación de frecuencia cero.
Estos diagnósticos ignoran flexión y pérdidas del relleno; no son necesariamente
los mínimos exactos de la curva de transmisión integrada.

## Ruta histórica v1: ley de masas

`noiz predict` conserva `mass-law-1`: placa infinita flexible, impermeable y sin
rigidez ni disipación, evaluada en centros nominales de 100 a 5000 Hz.
Con `x = πfm'/Z0`:

```text
τnormal = 1/(1 + x²)
TLnormal = 10 log10(1 + x²)
τdifusa = ln[(1 + x²)/(1 + x² cos²θmax)] / [x² sin²θmax]
TLdifusa = −10 log10(τdifusa)
```

Para `x = 1`, TL normal es `3.0102999566 dB`. Duplicar masa o frecuencia produce
un incremento tendente a `6.0206 dB` cuando domina la masa. Para `θmax = 90°`,
la transmisión difusa se reduce a `ln(1+x²)/x²`. Estas soluciones cerradas sirven
para verificar el límite sin rigidez de v2, igualando antes su definición de banda.

La frecuencia crítica y la resonancia de v1 eran diagnósticos separados. Abrir
un proyecto v1 en el editor v2 conserva la entrada y registra la migración, pero
calcularlo con v2 cambia las ecuaciones y el promedio espectral; no conserva el
resultado por diseño.

## Rw provisional

Se seleccionan las 16 bandas nominales de 100 a 3150 Hz. El contorno de referencia
es:

```text
f / Hz: 100 125 160 200 250 315 400 500 630 800 1000 1250 1600 2000 2500 3150
R / dB:  33  36  39  42  45  48  51  52  53  54   55   56   56   56   56   56
```

Se redondea la entrada a 0,1 dB con mitades alejadas de cero y se desplaza el
contorno en pasos enteros. Para cada desplazamiento se suma
`max(0, referencia desplazada − TL)`. Se elige el mayor cuya suma no supera 32 dB;
el valor a 500 Hz es Rw. Las décimas se evalúan como enteros para evitar decisiones
fronterizas por redondeo binario. No se añade la regla individual de 8 dB de STC.

El procedimiento se contrasta con Phonometry 3.3.0. La revisión normativa primaria
completa continúa pendiente: el resultado se presenta como **Rw orientativo**,
no como certificación ISO 717-1. El servicio no asigna Rw al modo de incidencia
normal. C/Ctr, STC y las clasificaciones de impacto todavía no están implementadas.

## Límites del resultado

Se rechaza calcular composiciones que soliciten bastidores acoplados, perfiles,
revestimientos de suelo, placas compuestas no admitidas o un panel poroso
independiente. Los datos pueden conservarse para su edición sin fingir que el
motor ya los resuelve. Una etiqueta suelo/cubierta no cambia la excitación aérea
a impacto o lluvia.

TL representa la relación de potencia del modelo. Un índice de laboratorio
requiere método y montaje de ensayo. La transmisión directa ideal no determina
R'w, DnT,w o L'nT,w entre recintos: faltan uniones, flancos y condiciones de salas.
Véanse [validación](validation.md) y [fuentes](sources.md).
