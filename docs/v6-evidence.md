# Evidencia científica y verificación de V6

La literatura sustenta las hipótesis y ecuaciones. La verificación numérica
comprueba su implementación. Una validación experimental requiere además
comparar predicciones con mediciones independientes y con entradas conocidas.
**Este registro no demuestra una precisión de ±3 dB ni equivalencia con INSUL.**

## Fuentes efectivamente consultadas

Se consultaron los ejemplares proporcionados por el usuario. Los números de
página siguientes corresponden a la paginación impresa, no al índice del visor
PDF. Los libros completos no se incluyen en el repositorio.

| Fuente y ubicación | Evidencia utilizable | Límites |
| --- | --- | --- |
| Bies, Hansen, Howard y Hansen, *Engineering Noise Control*, 6.ª ed., CRC Press, pp. 420–424, ecuaciones 7.45–7.60 | Resonancias de placa simplemente apoyada; impedancia flexional; integración angular; corrección por tamaño de panel mediante un límite angular dependiente del área y del perímetro | La extensión de placa infinita se considera válida por encima de 1,5 veces la primera resonancia. Una corrección de radiación finita por sí sola no resuelve los modos estructurales de baja frecuencia. |
| Mismo libro, pp. 440–442, §§7.2.8.9 y 7.2.9 | Efectos experimentales de montantes, y discusión de doble frente a triple hoja | Las expresiones para triple hoja sin conexiones mecánicas representan un límite ideal. No justifican que añadir hojas siempre mejore el aislamiento. No se presenta aquí validación de Quad. |
| Mismo libro, pp. 442–449, §7.2.11 y tabla 7.13 | Valores representativos medidos de TL en octavas para paneles, montantes y acristalamientos | Faltan dimensiones de probeta, propiedades mecánicas completas, pérdidas y detalles de montaje. Se pueden usar como contraste orientativo; no permiten calcular un error de predicción atribuible únicamente al modelo. |
| Vér y Beranek (eds.), *Noise and Vibration Control Engineering: Principles and Applications*, 2.ª ed., Wiley, 2005, pp. 439–442 | Distinción de ondas forzadas/libres, radiación de panel finito y pérdidas por material, estructuras conectadas y radiación | La formulación de transmisión descrita es válida por encima de la primera resonancia, donde domina la masa. La región de rigidez requiere la compliancia del panel. No se debe confundir una corrección de tamaño con un modelo modal. |
| Mismo libro, pp. 443–445, ecuaciones 11.109–11.114 | Recursión de impedancias y presiones para varias capas con continuidad de presión/velocidad y número de onda tangencial | Son capas infinitas lateralmente. El texto no valida la extensión de una corrección angular de placa única a conjuntos finitos de cuatro hojas. |
| Barron, *Industrial Noise Control and Acoustics*, Marcel Dekker, pp. 124–127, ejemplo 4-8 y tabla 4-3 | Caso calculado de dos vidrios de 6 mm con cámara de 75 mm; valores de resonancia y frecuencia crítica reproducibles | Los TL de esta tabla son cálculos aproximados, no mediciones. No son una curva experimental con la que ajustar V6. |
| Mismo libro, pp. 135–138, ejemplo 4-11 y tabla 4-5 | Espectro independiente y resultado STC = 25 según el procedimiento histórico 32/8 dB | Verifica la clasificación, no el predictor. No se describe una probeta que permita reproducir físicamente ese espectro. |

La página legal del ejemplar de *Engineering Noise Control* indica 2024 para la
6.ª edición, aunque el archivo recibido contiene 2023 en su nombre. Su DOI es
`10.1201/9780367814908`. El ejemplar de Barron indica copyright 2003 e ISBN
`0-8247-0701-X`, aunque el nombre del archivo contiene 2002. Se conservan estos
identificadores para evitar confundir ediciones y números de ecuación.

## Comprobaciones independientes reproducibles

### Clasificación publicada

[`validation/v6-rating-barron.json`](../validation/v6-rating-barron.json)
conserva los datos numéricos mínimos del ejemplo 4-11, su procedencia y su alcance.
[`tests/test_v6_literature.py`](../tests/test_v6_literature.py) comprueba que el
espectro publicado produce **STC = 25**, sin tolerancia en esa clasificación
entera. El motor usa explícitamente el procedimiento histórico: suma de
deficiencias ≤32 dB y deficiencia individual ≤8 dB. Este caso no demuestra
conformidad con una edición actual de ASTM E413 ni valida el cálculo de TL.

Para ejecutar esta comprobación desde la raíz:

```sh
uv run --locked --extra dev pytest tests/test_v6_literature.py
```

### Resonancias del ejemplo de doble acristalamiento

En el ejemplo 4-8 de Barron, cada vidrio tiene densidad de 2500 kg/m³, espesor
de 0,006 m, módulo de Young de 71 GPa y coeficiente de Poisson de 0,21. El
panel mide 1 × 2 m y la cámara tiene 0,075 m. El aire tiene densidad
1,188 kg/m³ y velocidad del sonido 345,6 m/s.

Con aritmética escalar independiente del predictor:

- Masa por hoja: `m = ρh = 15 kg/m²`.
- Rigidez: `D = Eh³/[12(1−ν²)] = 1336,959933 N·m`.
- Frecuencia crítica: `fc = c²/(2π) √(m/D) = 2013,5111 Hz`.
- Primera resonancia simplemente apoyada:
  `f11 = (π/2) √(D/m) (1/a² + 1/b²) = 18,53717 Hz`.
- Resonancia masa–aire–masa:
  `f0 = √[ρaire c² (1/m1 + 1/m2)/d]/(2π) = 79,93571 Hz`.

El libro publica aproximadamente 2014 Hz, 18,5 Hz y 79,9 Hz. Una comparación
con esos valores redondeados debe usar su resolución publicada (por ejemplo,
0,5 Hz para fc y 0,05 Hz para f11/f0), no interpretar ese redondeo como
incertidumbre experimental. Las curvas TL del mismo ejemplo no deben imponerse
como resultado esperado de un modelo distinto de placa finita.
El archivo `tests/test_v6_literature.py` comprueba estas frecuencias con los
helpers físicos y, para f0, también con el problema de autovalores de la cadena
masa–resorte utilizado por la aplicación.

### Integración y límites físicos

La p. 423 de Hansen especifica el promedio energético de los coeficientes de
transmisión dentro de cada banda, antes de convertir a dB. Recomienda al menos
20 frecuencias por banda para su procedimiento de integración. Cualquier
cuadratura alternativa más rápida necesita una comprobación de convergencia
frente a una referencia resuelta, en particular cerca de coincidencia y de las
resonancias de cámaras; aumentar la velocidad no justifica suavizarlas sin
control.

Las pruebas de conservación de energía para medios sin pérdidas, pasividad con
pérdidas, reciprocidad, límite de cámara nula y resonancias de masas acopladas
son verificaciones matemáticas. También deben comprobarse para tres y cuatro
hojas. No sustituyen los ensayos de esas configuraciones.

## Artículos identificados para validación independiente

Estos artículos se identificaron en la bibliografía de Hansen. **No se consultó
su texto completo durante esta revisión**; por tanto, no se atribuyen a ellos
curvas digitalizadas, tolerancias ni resultados adicionales a los descritos por
la fuente secundaria. El acceso de red de esta sesión no incluye los servidores
editoriales ni el repositorio NRC. La identificación bibliográfica no equivale
a una comprobación del artículo.

| Artículo | Publicación | Prioridad y propósito |
| --- | --- | --- |
| Davy (2009), “The forced radiation efficiency of finite size flat panels that are excited by incident sound” | *JASA* 126, 694–702 | Verificar radiación forzada finita y límites de aplicación. |
| Davy (2009), “Predicting the sound insulation of walls” | *Building Acoustics* 16, 1–20 | Comparar formulación de placa y corrección de tamaño. |
| Davy (2010), “The improvement of a simple theoretical model for the prediction of the sound insulation of double leaf walls” | *JASA* 127, 841–849 | Revisiones de doble hoja y supuestos de integración. |
| Davy, Guigou-Carter y Villot (2012), “An empirical model for the equivalent translational compliance of steel studs” | *JASA* 131, 4615–4624 | Compliancia de montantes y transmisión estructural. |
| Davy, Fard, Dong y Loverde (2019), “Empirical corrections for predicting the sound insulation of double leaf cavity stud building elements with stiffer studs” | *JASA* 145, 703–713 | Correcciones de montantes rígidos; separar ajuste y evaluación. |
| Bradley y Birta (2001), “On the sound insulation of wood stud exterior walls” | *JASA* 110, 3086–3096 | Ensayos de paredes con montantes; influencia de espaciado y conexión. |
| Quirt (1982), “Sound transmission through windows I: Single and double glazing” | *JASA* 72, 834–844 | Datos independientes para Single y Double sin confundir vidrio con muro de montantes. |
| Tadeu y Mateus (2001), “Sound transmission through single, double and triple glazing. Experimental evaluation” | *Applied Acoustics* 62, 307–325 | Candidato prioritario para contrastar Triple experimentalmente. |
| Brekke (1981), “Calculation methods for the transmission loss of single, double and triple partitions” | *Applied Acoustics* 14, 225–240 | Comparación entre familias de modelos y sus hipótesis. |

## Condiciones antes de declarar una precisión de predicción

Para cada ensayo hacen falta geometría y condiciones de borde, propiedades de
las hojas, pérdidas, cámaras, absorbente, conexiones, montaje, bandas, método de
ensayo, fuente primaria e incertidumbre disponible. Si faltan parámetros, deben
registrarse como desconocidos; ajustarlos hasta reproducir una curva convierte
esa curva en dato de calibración, no de evaluación independiente.

El banco debe conservar, por separado, casos de calibración y de evaluación.
Para estos últimos se informarán sesgo, error absoluto medio y error máximo
por banda, error de Rw/STC, cantidad de probetas y rango de configuraciones.
Las tolerancias numéricas se fijan con convergencia; las discrepancias físicas
se reportan frente a las mediciones, con su incertidumbre, sin ampliar un
umbral para forzar una aprobación.

No hay en esta revisión una serie experimental de cuatro hojas suficientemente
documentada. Que el solver pueda resolver Quad verifica su capacidad numérica;
su precisión física queda pendiente de ensayos independientes. Tampoco se
debe trasladar a Noiz Transmission un margen comercial de INSUL ni asignar el
nombre Sewell a una corrección diferente sin comprobar la formulación original.
