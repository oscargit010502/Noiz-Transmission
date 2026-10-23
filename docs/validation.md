# Verificación y validación científica

Para V6, véase [evidencia científica y verificación](v6-evidence.md): separa
las comprobaciones matemáticas, los ejemplos publicados y la validación
experimental que todavía falta para cuantificar la precisión del predictor.

Se distinguen tres afirmaciones: **el código resuelve las ecuaciones**, **las
ecuaciones representan el sistema físico** y **la clasificación cumple una norma
concreta**. Una no demuestra las otras. V4 (0.4.0) cuenta con verificación matemática y
contraste algorítmico; todavía no tiene un intervalo de error experimental para
sistemas comerciales.

## Nivel 1: verificación matemática

Los casos analíticos originales de [validation/cases.json](../validation/cases.json)
conservan derivaciones, unidades y tolerancias de v1. Las pruebas V2/V3 amplían
esa evidencia sin presentar los casos sintéticos como mediciones:

| Propiedad | Comprobación |
| --- | --- |
| Masa y placa flexible | Límites analíticos, TL normal exacta y recuperación de masa flexible cuando D=0 |
| Flexión | Frecuencia de coincidencia, signo disipativo y efecto de pérdidas |
| Cámaras | Límite de cámara pequeña y suma de masas; resonancia masa–aire–masa; cadena de cuatro masas con tres modos |
| Gases | Propiedades ideales, conservación de componente tangencial, límite de ángulo crítico, evanescencia, reciprocidad y conservación energética |
| Energía | Pasividad, conservación en sistemas sin pérdidas y reciprocidad al invertir la composición |
| Bandas | Límites exactos base 10 y promedio de transmisión con potencia uniforme por Hz |
| Integración | Convergencia cerca de coincidencia y resonancias estrechas de cámara |
| Porosos | Signo pasivo, reflexiones múltiples, Miki frente a Phonometry; lámina libre y Facing frente a productos de matrices independientes |
| Activación | Capas inactivas y cantidad cero no alteran resultados; cantidad de relleno equivale a su espesor efectivo |
| Fuga ideal | Geometría Slit/Aperture y mezcla energética; rechazo de área excesiva, doble contabilización y métodos no implementados |
| Resumen por octavas | Agregación ponderada por ancho de banda, sin promediar dB |
| Entradas | Rechazo de valores no físicos/no finitos, campos ambiguos y configuraciones no admitidas |

Las tolerancias de pruebas escalares miden error frente a una solución matemática;
no significan exactitud acústica del mismo orden. La tolerancia de integración
predeterminada del motor, **0,05 dB**, comprueba consistencia numérica y no el error de
predicción de una pared real. Si el integrador no resuelve una resonancia se
informa un error; ese caso no se convierte en un resultado válido por redondeo.

Las pruebas de guardado, migración, catálogo, interfaz y exportación verifican el
flujo de software. En V3 comprueban controles anidados, selección de producto,
activación de capas, parámetros que persisten al cambiar de modo, migración,
variantes ocultas inválidas, filtros de Floor Cover y rechazo de excitaciones no
implementadas. El render tiene pruebas de rotación real, zoom, orientación,
cuantidades y exclusión de datos inactivos. Estas pruebas permanecen separadas de
la evidencia de precisión física; una captura no valida un modelo.

Una regresión específica usa dos placas flexibles de 10,164445435 kg/m²,
separación 0,200568063 m e incidencia normal en la banda de 2500 Hz. La integral
analítica independiente da **47,23464153 dB**. Dos mallas globales insuficientes
podían coincidir cerca de 73,77 dB al omitir una resonancia: este caso demuestra
por qué la localización independiente de resonancias precede a la integración.
También se contrasta un caso difuso mediante el orden inverso de integración.

## Nivel 2: contraste independiente

Phonometry **3.3.0** contrasta el ajuste de Rw y las características Miki con las
mismas condiciones del aire y el mismo redondeo de coeficientes. Se usan además
integraciones y soluciones analíticas por caminos distintos cuando están
disponibles. Estos contrastes detectan errores de implementación; compartir una
correlación no transforma dos programas en dos experimentos independientes.

La documentación pública INSUL v10 y su bibliografía se revisaron para comprender
funciones, límites y fuentes; [el registro de consulta V3](v3-reference-review.md)
distingue páginas leídas de artículos primarios pendientes. **No se han comparado
espectros de salida de Noiz con ejecuciones de INSUL.** Las capturas aportadas
carecen de una especificación completa de todos los parámetros de cálculo y no
se tratan como expedientes reproducibles de validación.

Una comparación futura entre herramientas deberá fijar:

1. Versiones, modelo, incidencia, pérdidas, aire, geometría, uniones y bandas.
2. Qué entradas pueden hacerse equivalentes y qué física difiere. No ajustar
   propiedades sin trazabilidad para forzar coincidencia de un índice.
3. Curvas completas, diferencias por banda y procedencia de resultados.
4. Permisos para conservar/publicar entradas y resultados.

## Nivel 3: evidencia experimental

Cada espécimen de referencia debe incluir composición, dimensiones, montaje,
condiciones de borde, laboratorio/autores, método y edición de ensayo, bandas,
curva medida, informe o publicación, incertidumbre disponible y derechos de uso.
Un nombre comercial o un Rw sin curva y montaje no valida un modelo espectral.

Los XML recibidos son datos de catálogo, no una campaña experimental. V2 incluía
`Source = XXX` y curvas constantes de relleno. V3 incluye 669 curvas ΔL de Floor
Cover con etiquetas `Measured`/`Lab=True`, pero sin un informe específico asociado
no constituyen ensayos verificados. La elegibilidad de 1180 registros V3 para
placa isótropa —718 en el catálogo histórico V2— tampoco acredita sus propiedades.
Los nuevos montantes aportan dimensiones, no validación de un modelo de conexiones.

El protocolo experimental pendiente será:

1. Registrar fuentes, condiciones de uso y ausencia de incertidumbre cuando no
   esté publicada, sin inventar valores.
2. Separar especímenes de ajuste de los reservados para evaluación.
3. Definir antes del ajuste el dominio físico y métricas: sesgo, error absoluto por
   banda, RMSE espectral, máximos y error en Rw por familia.
4. Fijar tolerancias según uso e incertidumbre de ensayo; todavía no se promete
   precisión de ±N dB para Noiz.
5. Publicar fallos, exclusiones y sus motivos, así como versiones y entradas.
6. Delimitar validez solo para construcciones respaldadas por evidencia.

Las primeras familias deben ser placas homogéneas y dobles hojas mecánicamente
independientes. Paredes con montantes, ventanas finitas, laminados o placas gruesas
introducen fenómenos ajenos al modelo actual y requieren una evaluación específica.

## Nivel 4: clasificación normativa

Rw mantiene carácter provisional hasta revisar el texto completo de la edición
aplicable de ISO 717-1. La revisión deberá verificar bandas, redondeo a décimas,
contorno, pasos enteros, suma de desviaciones desfavorables, lectura a 500 Hz y
casos fronterizos. Coincidir con la API de otra biblioteca no certifica cumplimiento.

V2/V3 integran transmisión sobre bandas exactas; la selección de 100–3150 Hz para Rw
se realiza después de ese promedio energético. La curva de incidencia normal no
recibe Rw en el servicio. V1 conserva su evaluación por centros nominales y se
identifica por separado para evitar comparaciones de procedimientos diferentes.

V4 verifica por separado el procedimiento STC legado 32/8: contorno, bandas,
redondeo, déficits individuales y sumados, muescas, casos frontera y contraste
independiente; [v4-ratings.md](v4-ratings.md) explica su alcance provisional.
C/Ctr e índices de impacto requieren verificaciones propias antes de incorporarse. Las afirmaciones `Rw ±3 dB`, `Ln,w ±5 dB` y lluvia `±5 dBA` del
About de INSUL no son incertidumbres aplicables a Noiz. No se traslada a ISO 717 una regla particular de STC.

## Registro de una ejecución

Los comandos están en [reproducibility.md](reproducibility.md). Cada registro
concreto debe guardar versión del código, plataforma, entradas, condiciones,
curvas, advertencias, tolerancias y resultados de pruebas. Los recuentos y
resultados de una ejecución pertenecen a sus logs/CI; esta página describe el
protocolo y no sustituye esos registros.

La revisión de GUI V4 comprueba además clics reales en las flechas de incremento
y decremento, valores del modelo tras esos clics, filas completas y listas
accesibles con escalas de 100%, 125% y 150%. Las pruebas de perspectiva y
representación geométrica se distinguen de la validación acústica.
