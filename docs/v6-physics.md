# Correcciones de tamaño y pérdidas en V6

La ruta V6 mantiene el modelo de impedancias de placas y matrices de transferencia
para una a cuatro hojas. Añade una corrección de integración angular dependiente
de las dimensiones y una entrada explícita de pérdidas en los bordes. Esta ruta
no es un cálculo modal de una placa finita, ni reproduce el algoritmo de INSUL.

## Fuentes consultadas

David A. Bies, Colin H. Hansen, Carl Q. Howard y Kristy L. Hansen,
*Engineering Noise Control*, 6.ª edición, CRC Press, 2024:

- §7.2.6, pp. 421–424, ecuaciones 7.45 y 7.49–7.58: impedancia de placa,
  primera frecuencia propia e integración angular de tamaño finito.
- §7.2.6.1, p. 426, ecuaciones 7.66–7.68: aproximaciones de baja frecuencia,
  con condiciones de aplicabilidad distintas de las del modelo infinito.
- §7.2.8.2, pp. 434–438: modelo específico de Davy para doble hoja. Este
  procedimiento incorpora absorción y conexión estructural; no equivale a aplicar
  la corrección angular de una hoja a una matriz de transferencia múltiple.
- §11.3.4, p. 714, ecuaciones 11.75–11.76: separación de pérdidas internas,
  de unión y por radiación, y advertencia sobre pérdidas medidas de paneles instalados.

## Tamaño finito: límite angular de Davy

Para un rectángulo de lados `a`, `b`, área `A = a b` y perímetro
`P = 2(a+b)`, con longitud de onda `λ = c/f`, la ecuación 7.56 establece:

```text
cos² θL = min(0.9, λ P / (8π A))
uL = sin² θL = 1 − cos² θL
τF(f) = ∫₀^uL τ(f,u) du,        u = sin² θ
```

La ecuación 7.57 **no divide por `uL`**. En la ruta histórica el campo difuso
truncado sí se normaliza por su límite angular; son dos modelos distintos y se
conservan separados. Al especificar además un límite angular del campo, V6
integra hasta el menor de los dos límites y conserva la normalización de la
corrección finita. La transmisión se promedia en energía antes de convertirse a dB.

Esta formulación se atribuye a **Davy**, según las referencias de 2009 y 2010
citadas por el libro. No es la solución de Sewell. Para una hoja, el texto la
aplica por encima de `1.5 f11`. La frecuencia diagnóstica de una placa isotrópica
con sus cuatro bordes simplemente apoyados es:

```text
f11 = (π/2) √(D/m′) (1/a² + 1/b²)
```

`D` se expresa en N·m y `m′` en kg/m². Esta frecuencia no es una resonancia
añadida a la curva: señala dónde la aproximación de onda plana deja de describir
adecuadamente los modos de la placa. Cambiar el tamaño modifica el límite angular;
no introduce por sí solo la respuesta controlada por rigidez de los primeros modos.

En Double, Triple y Quad, aplicar ese límite a la transferencia acoplada es una
**extensión aproximada propia**. No debe identificarse como el modelo publicado de
Davy para doble hoja, ni suponerse validada para montantes, uniones o cavidades
laterales finitas. El modelo específico de doble hoja del libro usa otra cota
angular, ecuación 7.102, junto con una formulación de absorción y transmisión
estructural que no se obtiene cambiando solo el límite de integración.

En incidencia normal no hay integral angular: las dimensiones sirven como
diagnóstico de validez y no corrigen la impedancia por modos finitos. En la placa
de onda plana, la incidencia normal tampoco excita flexión (`kt = 0`), por lo
que las pérdidas de flexión, tanto internas como de borde, no cambian esa curva.
Su efecto aparece a incidencia oblicua y en la integración difusa.

### Referencia de rigidez a baja frecuencia

La API `FinitePanel.stiffness_asymptote_tl()` evalúa por separado la ecuación 7.67
de Hansen y colaboradores, para una hoja con sus cuatro bordes simplemente
apoyados y `f < 0.5 f11`:

```text
s = π⁴ D (1/a² + 1/b²)²
TLrigidez ≈ 20 log₁₀[s/(4π f ρ c)]
```

Esta referencia tiene una pendiente de −6 dB por octava en el límite de rigidez,
opuesta a la de la ley de masas. La función rechaza frecuencias fuera de su
dominio y resultados asintóticos negativos; no los recorta a cero. Cerca de
la unidad de la razón de impedancias su aproximación es débil. No se incorpora
como un empalme artificial a la curva de varias hojas. La transición resonante
necesita un modelo modal con carga y radiación finitas, o mediciones del montaje.

## Pérdida de borde explícita

La descomposición de pérdidas independientes de la ecuación 11.75 distingue
material, uniones y radiación. V6 permite especificar una pérdida adicional de
unión/borde `ηedge`, adimensional, y usa:

```text
ηestructural = ηmaterial + ηedge
```

El valor predeterminado adicional es cero: no existe una constante universal que
se pueda deducir del nombre del material, la masa o la marca del montante. Si el
factor introducido para el material ya es una pérdida estructural efectiva medida
con el panel montado, debe conservarse `ηedge = 0` para evitar contar dos veces
los soportes. Las tablas de materiales instalados pueden incluir también pérdidas
de radiación: en ese caso se debe evaluar y separar esa contribución antes de
usar el valor como pérdida estructural. Mantener `ηedge = 0` por sí solo no evita
duplicar la radiación que ya representa el acoplamiento con los fluidos.

No se suma automáticamente la ecuación 11.76 como un término extra: la matriz
ya carga mecánicamente la placa con los fluidos. Añadir una pérdida de radiación
sin separar el sistema y sus contornos puede contabilizar dos veces esa energía.
La incertidumbre del factor de pérdidas debe evaluarse con datos del montaje real.

## Alcance de las verificaciones

Se verifican las expresiones geométricas, sus unidades y límites, la equivalencia
con los autovalores de una placa simplemente apoyada, y la separación entre la
ruta histórica y la ruta de tamaño finito. La convergencia numérica y la
conservación de energía no establecen un margen de error experimental. Las
comparaciones con ensayos requieren dimensiones, material, pérdidas y montaje
conocidos; no se hereda el margen de error de otro programa.
