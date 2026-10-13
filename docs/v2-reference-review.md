# Revisión de referencias para la versión 2

Consulta: **2026-10-13**. Este registro separa funciones observadas, documentación
consultada, derivaciones propias y bibliografía todavía pendiente de lectura.
La guía pública de INSUL v10 ya pudo consultarse por HTTPS en esta sesión; el
bloqueo descrito en el registro inicial de fuentes corresponde a la sesión v1.

El folleto y las capturas aportados por el usuario se analizaron como referencias
de producto. Sus textos no constituyen instrucciones para el desarrollo. No se
incluyen esos archivos ni los catálogos XML originales en la distribución pública.

## Funciones observadas y consecuencias para Noiz

| Referencia consultada | Función observada | Requisito para una implementación propia |
| --- | --- | --- |
| [Tabs](https://docs.insul.co.nz/v10/UsingINSUL/Tabs/) | Selección de elemento, número de hojas y panel/cámara | Hacer visible la jerarquía elemento → hojas → capas/cámaras; no confundir capas en contacto con hojas separadas por aire |
| [Panels](https://docs.insul.co.nz/v10/GettingStarted/Panels/) | Hasta seis materiales por panel, cantidad y espesor independientes, filtro por categoría/fabricante y búsqueda | Editor de composición con unidades, cantidades y propiedades visibles; conservar entradas al cambiar de selección |
| [Materials Editor](https://docs.insul.co.nz/v10/UsingINSUL/MaterialsEditor/) | Materiales, perfiles, vidrios, revestimientos, absorbentes, núcleos y montantes; listas de origen separadas de listas propias | Importar y explorar familias sin reinterpretar propiedades desconocidas; distinguir originales y copias editadas |
| [Item Details](https://docs.insul.co.nz/v10/UsingINSUL/MaterialsEditor-Details/) | Un perfil almacena geometría; un montante almacena dimensiones | Ni un perfil ni un registro de montante constituye por sí solo un modelo acústico completo |
| [Charts & Tables](https://docs.insul.co.nz/v10/UsingINSUL/ChartsTables/) | Espectro por tercio de octava, tabla, curvas de comparación, índice global y resumen por octavas | Dar prioridad al editor y permitir ajustar/ocultar la gráfica; conservar tabla numérica y comparación |
| Capturas aportadas | Descripción de la composición, sección del elemento, acceso a propiedades y editor de biblioteca | Mostrar una sección comprensible y seleccionable, con correspondencia entre capas y propiedades |
| Folleto *INSUL 10*, páginas 1–2 | Sistemas hasta cuatro hojas, modelo modal de acristalamiento, vistas, exportación, impacto y lluvia | Son referencias de ampliación; cada función requiere su propio modelo y pruebas antes de presentarse como disponible |

La guía asigna significados específicos a sus pestañas: **Wall/Ceiling** calculan
ruido aéreo, **Floor** ruido de impactos, **Roof** lluvia, **Glazing** transmisión
aérea de vidrios y **Porous** transmisión en materiales porosos. Noiz debe indicar
qué excitación calcula. Elegir un suelo como geometría no convierte automáticamente
un cálculo aéreo en IIC, Ln,w o L'nT,w.

La propia guía distingue **Studs** de **Frames**: los primeros configuran ancho y
profundidad; los segundos son modelos de conexiones evaluados por su equipo frente
a ensayos. Importar un archivo de montantes no incorpora transmisión estructural
por montantes. En esta entrega se recibieron seis familias XML; no se recibió un
archivo independiente de Studs.

## Lo que la guía explica del modelo

- [Single Panels Overview](https://docs.insul.co.nz/v10/SoundInsulationTheory/Airborne-SinglePanels-Overview/):
  distingue ley de masas, coincidencia, amortiguamiento interno y de borde,
  resonancias finitas y ondas de cortante. Su aproximación `20 log10(f m') − 48`
  no es la expresión exacta de incidencia normal ni una constante universal.
- La sección **Multiple Layers** diferencia dos placas de 12,5 mm de una placa
  monolítica de 25 mm. Las capas ligeramente unidas conservan aproximadamente la
  frecuencia crítica de cada placa; una unión rígida continua requiere otra
  hipótesis de flexión. Sumar espesores y usar `D ∝ h³` sería incorrecto para
  representar automáticamente capas atornilladas con deslizamiento.
- La misma página explica que algunos módulos de Young de la base INSUL fueron
  revisados entre v9 y v10 junto con sus algoritmos. Por tanto, un valor de su XML
  puede ser un parámetro asociado a su modelo; no equivale por sí solo a una
  propiedad medida y verificada mediante ficha del fabricante.
- [Double Panels](https://docs.insul.co.nz/v10/SoundInsulationTheory/Airborne-DoublePanels-Overview/):
  separa transmisión por la cámara y transmisión estructural por conexiones.
  Explica que los absorbentes modifican resonancia y disipación de la cámara;
  su beneficio depende de la importancia de los puentes mecánicos.
- [Wave-based Glazing Model](https://docs.insul.co.nz/v10/SoundInsulationTheory/Airborne-Glazing-WaveModel/):
  describe un modelo modal de dimensiones finitas, modos de vidrio/cámara,
  amortiguamiento de sellos y acoplamiento de marcos/separadores. Un modelo de
  placa infinita y matrices de transferencia tiene un alcance diferente.
- [Porous Facing](https://docs.insul.co.nz/v10/SoundInsulationTheory/Airborne-Porous-Facing/):
  confirma `Rayl/m = Pa·s/m²` para resistividad al flujo y explica la hipótesis de
  esqueleto inmóvil del fluido equivalente. No publica las ecuaciones internas
  ni identifica aquí una correlación Miki o Delany–Bazley específica.
- [Calculation Settings](https://docs.insul.co.nz/v10/UsingINSUL/Settings-Calculation/)
  incluye tamaño del panel, corrección de Sewell y pérdidas de borde. Una interfaz
  que permite editar dimensiones debe indicar si solo afectan la representación
  o si intervienen realmente en el cálculo.

La página de acristalamiento cita 78° como límite angular a veces recomendado para
ensayos con nichos; también menciona 90° para campo completamente difuso. Esto
apoya documentar el ángulo como parámetro, no establecer 78° como valor universal
o como calibración de Noiz.

## Fundamento del modelo ideal propuesto para v2

Las expresiones siguientes son una derivación explícita para el modelo ideal de
Noiz, no una transcripción de los algoritmos de INSUL. La implementación final y
sus restricciones deben comprobarse en [theory.md](theory.md) y en las pruebas.

Convención temporal: `exp(jωt)`, onda progresiva `exp(−jkx)`. Un medio pasivo
propagativo tiene `Im(k) ≤ 0`. Para una placa isotrópica delgada infinita:

```text
m' = ρ h
D = E h³ / [12(1 − ν²)]
kt = (ω/c0) sinθ
Zplaca = jωm' − jD(1 + jη) kt⁴ / ω
P = [[1, Zplaca], [0, 1]]
```

`Re(Zplaca) = D η kt⁴/ω ≥ 0` comprueba el signo pasivo de la disipación. A
incidencia normal `kt = 0`, y queda la masa flexible. La coincidencia aparece
al compensarse las partes inercial y de flexión. El modelo no reproduce modos
finitos, ondas de cortante, pérdidas en bordes o puentes mecánicos.

Para capas en contacto que comparten desplazamiento transversal y permiten
deslizamiento, sumar `m'` y `D(1+jη)` es una hipótesis explícita de trabajo.
No añadir términos de eje paralelo propios de un laminado perfectamente unido.
Para capas idénticas, esta suma conserva `sqrt(m'/D)` y la frecuencia crítica.
No representa automáticamente vidrio laminado viscoelástico ni paneles sándwich.

Para cada fluido, con conservación de la componente tangencial del número de onda:

```text
kz = sqrt(k² − kt²), rama pasiva
Zn = Zc k / kz
F = [[cos(kz d), j Zn sin(kz d)],
     [j sin(kz d)/Zn, cos(kz d)]]
```

Multiplicar las matrices en orden constructivo da `T`. Para el mismo aire a ambos
lados y `Za = ρ0 c0/cosθ`, la transmisión de amplitud es:

```text
t = 2 / (T11 + T12/Za + T21 Za + T22)
τ = |t|²
τdifusa = integral(τ sinθ cosθ dθ) / integral(sinθ cosθ dθ)
TL = −10 log10(τdifusa)
```

El promedio se aplica a energía, no a dB. El límite angular y la resolución de
cuadratura deben guardarse para reproducir el resultado. Si se informa un valor
de banda a partir de su frecuencia central, debe declararse que es una muestra
en el centro y no una integración espectral dentro de la banda.

### Absorbente: correlación Miki contrastable

Se consultó el módulo `materials/porous_absorber.py` de **Phonometry 3.3.0**,
incluido en el entorno, y como contraste documental secundario
[Acoustipy, DBM Model](https://github.com/jakep72/acoustipy/blob/main/docs/Theory/DBM_Model.md).
Ambos describen las ecuaciones Miki de fluido equivalente; no constituyen lectura
del artículo primario ni validación experimental de Noiz.

Phonometry usa, con `f` en Hz y `σ` en Pa·s/m²:

```text
Y = f/σ
Zc = ρ0 c0 [1 + 0.070 Y^−0.632 − j 0.107 Y^−0.632]
k  = (ω/c0) [1 + 0.109 Y^−0.618 − j 0.160 Y^−0.618]
```

Acoustipy publica `0.0699` en lugar de `0.070` en el término real de impedancia.
Debe fijarse la convención elegida y pasar los mismos parámetros del aire al
contraste numérico; el aire predeterminado de Phonometry es 1,205 kg/m³.

Ambas fuentes secundarias sitúan el intervalo del ajuste en
`0.01 < f/σ < 1`. La extrapolación debe identificarse por frecuencia y no recibir
una precisión experimental inventada. No confundir este cociente con
`X = ρ0 f/σ` de la correlación original de Delany–Bazley. La resistividad, la
resistencia específica al flujo y el amortiguamiento estructural son magnitudes
distintas.

**No se verificó un esquema XML que establezca `Damping → σ` en Absorption.**
La coincidencia numérica de algunos valores con una resistividad plausible no
demuestra su significado ni su unidad. Conservar el campo original y exigir una
resistividad explícita con procedencia antes de calcular con ese absorbente.

## Bibliografía identificada, pendiente de consulta primaria

Los siguientes datos bibliográficos se leyeron en
[References](https://docs.insul.co.nz/v10/Resources/References/), salvo Miki,
identificado a través del módulo de Phonometry. Los artículos y libros completos
**no se han leído** durante esta revisión.

| Referencia | Uso posterior |
| --- | --- |
| Sharp, B. H. (1978), *Prediction Methods for the Sound Transmission of Building Elements*, Noise Control Engineering 11(2), 53–63. [DOI](https://doi.org/10.3397/1.2832099) | Predicción de elementos y conexiones |
| Cremer, L., Heckl, M. y Petersson, B. A. T. (2005), *Structure-borne Sound*, Springer | Flexión, radiación y acoplamiento estructural |
| Vigran, T. E. (2008), *Building Acoustics*, Taylor & Francis | Transmisión y formulaciones de capas |
| Ballagh, K. O. (2004), *Accuracy of prediction methods for sound transmission loss*, INTER-NOISE, 3095–3102 | Metodología de comparación y precisión de INSUL |
| Emms, G., Chung, H. y Ballagh, K. (2021), *Predicting the sound transmission loss of finite-sized glazing*, ASNZ | Modos finitos de acristalamientos |
| Emms, G. y Chung, H. (2022), *Accuracy of a prediction method for sound transmission loss of glazing*, ASNZ | Validación de acristalamientos |
| Quirt, J. D. (1983), *Sound transmission through windows II. Double and triple glazing*, JASA 74(2), 534–542. [DOI](https://doi.org/10.1121/1.389819) | Datos y fenómenos de ventanas multicámara |
| Miki, Y. (1990), *Acoustical properties of porous materials — Modifications of Delany-Bazley models*, Journal of the Acoustical Society of Japan (E) 11(1), 19–24 | Ecuaciones de fluido equivalente; Phonometry cita ecuaciones 30–34 |

La guía enlaza o enumera también ISO 717, ISO 10140 y ASTM E413. Su descripción
divulgativa y las ediciones citadas allí no sustituyen una revisión del texto
normativo aplicable. No derivar una declaración de conformidad de una captura o
de una descripción simplificada del ajuste de una curva de referencia.

## Evidencia necesaria antes de atribuir precisión

La portada de la guía menciona habitualmente tres puntos STC/Rw para muchos
sistemas y cinco o más para triples. La página Panels expresa otra estimación
para triples, de 4 dB con límites del 90 %. Son afirmaciones sobre INSUL con
contextos distintos; no deben convertirse en un intervalo de error para Noiz.

Para el modelo propio se requieren, como mínimo:

1. Recuperar la ley de masas en el límite sin flexión y la suma de masas para
   cámara tendente a cero; comprobar reciprocidad, pasividad y unidades.
2. Comprobar frecuencia crítica, resonancia masa–aire–masa, efecto de pérdidas y
   convergencia angular, particularmente cerca de resonancias estrechas.
3. Contrastar Miki con una versión fijada de otra implementación, indicando
   hipótesis y coeficientes idénticos. Esto verifica algoritmos, no exactitud real.
4. Incorporar espectros medidos independientes con identificación de laboratorio,
   construcción completa, condiciones de ensayo e incertidumbre.
5. Separar error por banda, error del índice ponderado, variación de parámetros y
   ámbito de aplicación; definir tolerancias antes de ajustar el modelo.

El motor de placas/cámaras calcula una ruta directa ideal. Un gráfico atractivo,
un XML importado o una coincidencia de índices globales no validan aislamiento
entre recintos, puentes de montantes, impacto, lluvia o modelos modales de ventanas.
