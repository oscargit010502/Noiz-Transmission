# Verificación de V7.1

Esta revisión utiliza el artículo de B. H. Sharp, *Prediction Methods for the
Sound Transmission of Building Elements*, **Noise Control Engineering 11(2),
53–63 (1978)**, aportado por el usuario. Las ecuaciones y sus subíndices se
comprobaron en las páginas renderizadas del PDF. La extracción de texto se usó
para localizar contenido, no para decidir constantes o unidades ambiguas.

## Comprobación numérica independiente

El ejemplo de diseño de las páginas 62–63 ofrece un control que no depende de
copiar la ecuación implementada: a partir de un objetivo de **58 dB a 1.000 Hz**,
se calcula primero la masa necesaria con las ecuaciones inversas 25 y 26. Para
dos hojas iguales, `fc = 4.000 Hz` y una separación de conexiones de `0,61 m`:

| Unión | Masa total obtenida por la ecuación de diseño | TL de la vía estructural al sustituir en la ecuación directa |
| --- | ---: | ---: |
| Puntual en una hoja | 29,0142 kg/m² | 57,9794 dB |
| Lineal en ambas hojas | 64,0184 kg/m² | 57,9794 dB |

La diferencia de 0,0206 dB con el objetivo viene de las constantes redondeadas
99 y 72 de las ecuaciones inversas: `20 log10(2)` no es exactamente 6 dB.
Las masas aproximadas que publica el artículo son 29 y 64 kg/m².

La prueba de dos contactos puntuales utiliza las impedancias de la ecuación 17
y las ecuaciones 20 y 22. Para hojas de 10 y 15 kg/m², frecuencias críticas de
2.500 y 4.000 Hz y separación equivalente de 0,61 m, se obtiene 60,4926 dB
a 1.000 Hz. Este caso no utiliza la aproximación de una sola hoja puntual de
la ecuación 23. Tampoco se identifica la aproximación lineal 24 con las
ecuaciones 21–22: no son algebraicamente equivalentes.

Este control comprueba el cálculo de la vía por puentes en su región de
aplicación. El TL total puede ser menor al añadir la vía aérea en energía. No
demuestra una tolerancia experimental del programa ni un valor Rw/STC ensayado.

Los 17 controles independientes de `tests/test_v71_reference_checks.py`
comprueban esas sustituciones, intercambio de hojas conservando la geometría
de contacto, densidad de conexiones, resonancia frente a un problema de dos
osciladores, suma de energías, pasividad y distinción entre cámara vacía y
rellena. En los casos de núcleo con relleno se declara una resistividad
sintética de 20.000 Pa·s/m²; esto no verifica que un producto comercial tenga
ese valor ni la política de selección de la aplicación.

La ruta automática combina la vía aérea Davy/Hansen con la vía rígida Sharp.
Las verificaciones separadas de ambas ecuaciones no validan experimentalmente
esta combinación. En particular, prolongar la asíntota estructural por la
región de coincidencia, resolver automáticamente un tipo de contacto y elegir
una resistividad genérica son hipótesis que deben acompañar al resultado.
Un puente rígido tampoco constituye un límite inferior universal para toda
frecuencia o todo aislador comercial.

## Qué permiten comparar los ensayos del artículo

La figura 12, p. 61, muestra una doble pared de yeso de 15,9 y 9,5 mm, con
montantes de madera cada 0,61 m y fibra de vidrio en la cámara. La discusión
posterior permite asociar a esas hojas masas nominales de 12,6 y 7,3 kg/m² y
frecuencias críticas de aproximadamente 2.500 y 4.000 Hz. La ecuación 24 da una
asíntota estructural de 43,8607 dB a 500 Hz y 49,8813 dB a 1.000 Hz.

Sin embargo, la figura no es una tabla de resultados de laboratorio y no
especifica por sí sola profundidad de cámara, pérdidas de ambas hojas, montaje
perimetral y caracterización completa del absorbente. Se conserva como contraste
de tendencias; no se digitaliza una curva para afirmar una precisión en dB ni
se ajustan propiedades ausentes para conseguirla. La figura 13 contiene además
inconsistencias tipográficas de unidades y de número de ecuación que impiden
tratar su pie como una especificación de montaje completa.

## Distinciones físicas que no deben ocultarse

- Una unión de tornillos a un ala continua no pasa a ser una conexión puntual
  solamente por el tamaño de los tornillos. Sharp identifica montantes ordinarios
  de madera y metal como conexiones lineales; la conexión puntual descrita exige
  un contacto localizado de la hoja.
- Las expresiones aéreas de tres regiones de Sharp suponen una cámara
  suficientemente amortiguada. Sus ensayos de las pp. 56–58 muestran que una
  cámara vacía puede transmitir mucho más; no se le asigna automáticamente la
  curva del caso absorbente.
- El valor `113/sqrt(me*d)` publicado junto a la ecuación 6 y el ejemplo de
  diseño no coincide con la frecuencia del sistema adiabático de dos masas y
  un resorte de aire. Si se usan ambos, deben identificarse como magnitudes
  distintas, sin rebautizar una transición aproximada como una resonancia
  calculada desde las propiedades del aire.
- La mejora por separación, aisladores o doble bastidor depende del camino
  mecánico que permanece. Un nombre comercial no acredita su amortiguamiento
  dinámico, carga de diseño o independencia estructural.

Las comprobaciones de implementación y las hipótesis de selección automática
deben leerse junto a la [revisión de fuentes](v71-reference-review.md).
