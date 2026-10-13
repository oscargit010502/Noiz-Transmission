# Modelo físico y clasificación

La versión 3 (0.3.0) amplía el modelo propio de transmisión aérea por placas
isótropas infinitas, cámaras con gas y capas porosas. El identificador se mantiene
como `transfer-matrix-plate-1`; para reproducir una ejecución también es necesario
guardar la versión de software o commit, porque ese nombre no distingue V2/V3.
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

## Placa infinita con masa, flexión y pérdidas

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

La curva V2/V3 incorpora la flexión. Esta frecuencia sigue siendo un diagnóstico de
placa ideal: no es un modo propio de una placa finita ni un dato experimental.
El modelo no incorpora cizalladura en placas gruesas, condiciones de borde,
radiación finita, dimensiones modales o amortiguamiento de fijaciones.

### Varias capas dentro de una hoja

Una hoja admite hasta seis capas, cada una con cantidad `n_i` entre 1 y 10.
Las capas desactivadas se conservan en el proyecto y se excluyen de estas sumas.
Se supone que
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

## Cámaras de aire o gas y relleno poroso

Se admiten una a cuatro hojas, con exactamente una cámara entre hojas consecutivas.
La configuración Quad comprende cuatro hojas y tres cámaras, no cuatro cámaras.
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
No se modela contacto mecánico del absorbente con las hojas. En el editor, el
espesor efectivo del relleno es cantidad por espesor unitario; cantidad cero lo
excluye sin borrar las propiedades guardadas.

### Gases de cámara

Aire usa `ρ0` y `c0` exteriores. Para argón, kriptón y xenón la aplicación obtiene
propiedades de gas puro ideal a `T = 293.15 K` y `P = 101325 Pa`:

```text
ρg = P M / (R T)
cg = sqrt(γ R T / M)
k = ω/cg
Zc = ρg cg
```

`R = 8.31446261815324 J/(mol·K)`, `γ = 5/3` para estos gases monoatómicos y masas
molares de 0.039948, 0.083798 y 0.131293 kg/mol respectivamente. La API física
permite introducir directamente densidad/velocidad de un gas, o cambiar T/P al
consultar `ideal_gas_properties`; esos parámetros no son controles ambientales
por cámara del editor V3. La misma función admite aire ideal con
`M = 0.02896546 kg/mol`, `γ = 1.4`, pero seleccionar Air en el proyecto conserva
los valores exteriores configurados.

El medio exterior continúa siendo aire. Se conserva `kt` exterior en cada cámara;
la raíz compleja `kz` incorpora propagación evanescente cuando corresponda. La
matriz usa el límite finito al aproximarse `kz` a cero. No se modelan mezclas,
humedad, gradientes térmicos o pérdidas termoviscosas del gas. El relleno Miki,
ajustado para aire, se rechaza si se intenta combinar con un gas noble.

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

### Facing y lámina Porous independiente

`Facing` agrega una capa Miki al lado incidente de un único panel sólido. Su
matriz se multiplica antes de la placa; no se convierte en masa o rigidez de
placa. El espesor efectivo es cantidad por espesor unitario. Se excluye al
desactivar Facing o asignar cantidad cero. La aplicación rechaza Facing activo
con más de una hoja o simultáneamente con el modo Porous.

`Porous` calcula la transmisión a través de una lámina Miki libre entre dos
semiespacios de aire. Usa espesor y resistividad explícitos, sin placa ni respaldo
rígido. Las capas sólidas que puedan conservarse en el proyecto no participan.
Su resultado es TL aéreo, no coeficiente de absorción. La masa superficial se
informa como cero en el contrato numérico porque no se infiere una masa sólida de
la resistividad; no debe interpretarse como densidad real nula del absorbente.

## Transmisión y promedio energético

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

La salida usa etiquetas nominales de 50 a 5000 Hz, pero la integración V2/V3 emplea
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
valor en el centro nominal como sustituto de la integral en banda.

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

### Resumen por octavas

Se reúnen los tercios contiguos en siete bandas nominales de 63 a 4000 Hz. Con
`Δfi` igual al ancho exacto del tercio, el resumen calcula
`τoct = Σ(Δfi · 10^(−TLi/10))/ΣΔfi` y `TLoct = −10 log10(τoct)`.
Conserva la hipótesis de potencia uniforme por Hz; no promedia dB.

## Abertura ideal y diagnósticos

V3 admite una abertura geométrica con método explícito `open_area`: para Slit,
`Sabertura = altura × longitud`; para Aperture, `Sabertura = π radio²`. Tras
convertir mm a m, `p = Sabertura/(ancho × alto del elemento)`. Se exige `0 < p ≤ 1`
al activarla. Sigue disponible la entrada histórica
`p = leak_percentage/100`, pero no se permite activarla simultáneamente con una
fuga geométrica. La combinación ideal con transmisión unitaria por abertura es:

```text
τtotal = (1 − p) τplacas + p
TLtotal = −10 log10(τtotal)
```

A altas prestaciones el límite es `−10 log10(p)` dB cuando `p > 0`. No es un
modelo de rendijas o agujeros con difracción, profundidad, sellos o resonancias.
No reproduce las rutinas de fugas de INSUL. Los controles Gomperts y Mechel,
posición, profundidad, masas de sellado y relleno se guardan, pero elegir esos
métodos bloquea el cálculo; no se sustituyen silenciosamente por `open_area`.
Véase la evidencia disponible en [referencias V3](v3-reference-review.md).

La masa superficial informada suma solo placas sólidas activas, sin masa de
estructura, absorbente de cámara o Facing. Ancho y alto no modifican el modelo
infinito; sí cambian el área relativa de una fuga geométrica. El espesor total
incluye placas y cámaras, más Facing activo; en Porous es el espesor de la lámina.

Para dos hojas, el diagnóstico concentrado de aire sin pérdidas es:

```text
f0 = sqrt[(ρ0c0²/d)(1/m'1 + 1/m'2)] / (2π)
```

Para dos, tres o cuatro hojas se usa la cadena acoplada de masas y muelles de gas:
cada cámara aporta rigidez `s_i = ρg cg²/d_i` a las dos masas vecinas. Las raíces de
los autovalores no nulos de `M^−1/2 K M^−1/2`, divididas por `2π`, dan `N−1`
frecuencias diagnósticas para `N` hojas. Se excluye el modo de traslación de
frecuencia cero.
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
para verificar el límite sin rigidez de V2/V3, igualando antes la definición de banda.

La frecuencia crítica y la resonancia de v1 eran diagnósticos separados. Abrir
un proyecto v1 en el editor actual conserva la entrada y registra la migración, pero
calcularlo con el motor actual cambia las ecuaciones y el promedio espectral; no conserva el
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

Se rechaza calcular composiciones que soliciten bastidores acoplados o montantes,
perfiles, Floor Cover, placas compuestas/anisótropas no admitidas, relleno Miki con
gas noble o métodos Gomperts/Mechel. Activar excitación de impacto o lluvia también
bloquea la predicción; sus controles se guardan sin inventar curvas ni índices.
El modo aéreo explícito de suelo/cubierta sigue siendo transmisión aérea ideal.

Floor Covering puede mostrar ΔL declarado de un registro y su tipo de suelo base;
ese espectro no equivale a Ln de la construcción completa ni es una predicción
propia de impacto. Su etiqueta Measured no acredita un informe de ensayo.

TL representa la relación de potencia del modelo. Un índice de laboratorio
requiere método y montaje de ensayo. La transmisión directa ideal no determina
R'w, DnT,w o L'nT,w entre recintos: faltan uniones, flancos y condiciones de salas.
Véanse [validación](validation.md) y [fuentes](sources.md).
