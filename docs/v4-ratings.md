# Selección de índices en V4

El selector **Rw / STC** clasifica el mismo espectro de transmisión aérea sin
recalcular el modelo físico. STC se calcula con su propia curva y su intervalo
de frecuencias: no es un cambio de nombre de Rw. La incidencia normal no recibe
ninguno de los dos índices. Son resultados orientativos de una predicción, no
resultados certificados de un ensayo.

## Procedimiento STC disponible

Identificador reproducible: `STC-legacy-32-8-whole-dB-v1`.

- Dieciséis bandas nominales de tercio de octava de **125 a 4000 Hz**.
- Contorno relativo a 500 Hz: `-16, -13, -10, -7, -4, -1, 0, 1, 2, 3, 4, 4, 4, 4, 4, 4` dB.
- TL redondeado a dB enteros, con mitades alejadas de cero.
- Desplazamiento del contorno en pasos de 1 dB hasta el mayor valor que
  satisfaga simultáneamente una suma de déficits **≤ 32 dB** y cada déficit
  individual **≤ 8 dB**. Las dos igualdades son admisibles.
- STC es la ordenada a 500 Hz del contorno desplazado; es una clase, sin unidad.
- No se interpolan bandas ausentes. Los datos no finitos, los duplicados y las
  frecuencias no nominales se rechazan. Las bandas adicionales de 50, 63, 80,
  100 y 5000 Hz se validan pero no intervienen en STC.

La guía pública de INSUL 10 describe el procedimiento de suma 32 / límite 8,
pero su bibliografía cita ASTM E413-16 sin resolver las convenciones de cada
edición. Esta implementación se identifica expresamente como **procedimiento
legado 32/8 provisional**: no afirma conformidad con una edición normativa de
ASTM E413 ni pretende resolver discrepancias entre ediciones. Antes de emplear
el índice para una exigencia reglamentaria hace falta revisar la edición
normativa aplicable y validarlo con resultados trazables de laboratorio.

El criterio Rw existente mantiene su intervalo **100–3150 Hz**, su redondeo a
0,1 dB y la suma de déficits ≤ 32 dB, sin límite individual de 8 dB. Una muesca
profunda puede producir diferencias apreciables entre ambos índices.

## Trazabilidad y verificación

Fuentes consultadas el 15 de octubre de 2026:

- [INSUL 10, Airborne Ratings](https://docs.insul.co.nz/v10/SoundInsulationTheory/Ratings-Airborne/):
  intervalo STC y procedimiento suma 32 / límite 8. No se heredan las
  declaraciones de precisión de INSUL para Noiz Transmission.
- [INSUL 10, References](https://docs.insul.co.nz/v10/Resources/References/):
  referencia bibliográfica a ASTM E413-16; la norma íntegra no se ha usado como
  prueba de conformidad.
- [python-acoustics, building.py](https://github.com/python-acoustics/python-acoustics/blob/master/acoustics/building.py),
  contrastado con la distribución **acoustics 0.2.6**: contorno STC y un caso
  independiente de curva suave. La dependencia no se incorpora al producto y
  no se ha copiado su implementación. Su condición de déficit individual no
  se emplea como referencia de validación del límite 8 dB.

Para TL `[23,25,28,29,30,34,36,40,42,43,43,43,44,45,45,46]` dB, Noiz y
python-acoustics 0.2.6 dan **STC 40**, con suma de déficits 27 dB y máximo 6 dB.
Las pruebas adicionales cubren igualdad exacta en ambos límites, muescas,
invariancia ante desplazamientos enteros, redondeo, datos inválidos y una
búsqueda exhaustiva independiente de contornos en espectros aleatorios.

CSV y HTML incluyen el STC y el identificador del procedimiento. La propiedad
`AssemblyPrediction.stc_db` es calculada a partir del espectro; no añade campos
al proyecto y conserva compatibilidad con el esquema de guardado 3.

## Índices de impacto

**IIC** —no ICC— y **Ln,w** requieren un espectro de nivel de impacto. El motor
de impacto sigue pendiente; por eso el selector no muestra valores para ellos.
No se derivan de TL ni de la curva de mejora ΔL de un revestimiento de suelo.

**L’nT,w** es el nivel de impacto estandarizado entre recintos; depende de la
normalización respecto al tiempo de reverberación y del edificio. No equivale
a Ln,w del elemento. Mostrarlo como sustituto de Ln,w exigiría añadir el modelo
y las entradas del recinto correspondientes.
