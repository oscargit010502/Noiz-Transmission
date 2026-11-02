# Verificación y referencias de V7

Las comprobaciones matemáticas, la comparación con una publicación y la
validación experimental responden a preguntas distintas. Noiz no hereda una
tolerancia en dB de Davy, Strutt, INSUL ni de los libros consultados.

## Ecuaciones comprobables

La referencia principal de las comprobaciones independientes es *Engineering
Noise Control*, 6.ª edición, capítulos 6 y 7:

- Radiación de panel finito: ecuación 6.91, p. 383. La expresión auxiliar es
  `H = [0.67 sqrt(2ka/π) − 0.124]⁻¹`; los corchetes son importantes y se
  comprobaron en la página renderizada del PDF, no únicamente en su extracción
  de texto. La eficiencia de radiación puede ser mayor que uno: no es un
  coeficiente de transmisión energética limitado a uno.
- Radiación por excitación mecánica: §4.15, pp. 242–243, ecuaciones
  4.180–4.186. Se distingue de la radiación forzada por un campo acústico:
  el propio texto establece esa separación en §11.3.1, p. 707. La referencia
  cruzada de 7.93 a §6.8.2 entra en conflicto con esta distinción, pues §6.8.2
  explica que su fórmula se sustituyó respecto a ediciones anteriores.
  Aplicar indiscriminadamente 6.91 a los factores resonantes de transmisión
  por montantes puede producir transmisiones mayores que uno para paredes
  ordinarias. Esto se debe resolver por el mecanismo de excitación, no mediante
  un recorte de TL que oculte la inconsistencia.
- Resonancia masa–aire–masa con flexión entre montantes: ecuaciones 7.89–7.92,
  pp. 434–435. El resultado para dos hojas idénticas se puede contrastar con
  la raíz mayor de un problema de dos osciladores acoplados.
- Transmisión por conexiones puntuales y lineales: ecuaciones 7.93–7.96,
  pp. 435–436. Los factores `Q` y `R` cambian entre ambas formulaciones.
  La flexibilidad puntual tiene unidades m/N; la flexibilidad por línea tiene
  unidades m²/N, según el balance dimensional de la ecuación 7.95. No son
  entradas intercambiables.
- Suma de caminos: ecuaciones 7.88 y 7.107. Se suman coeficientes de transmisión,
  no valores TL en dB. Dos caminos de igual transmisión reducen el TL total
  en `10 log10(2)` respecto al TL de cada camino.
- La tabla 7.8 usa `g`, descrito como *gauge*, en su ajuste empírico. El texto
  no especifica una conversión universal desde espesor en mm. Esa ambigüedad
  debe conservarse explícita; no justifica sustituir `g` por un espesor ni
  deducirlo automáticamente de un nombre comercial.

Un resultado matemático finito no garantiza que una aproximación sea aplicable
a cualquier geometría. Por ejemplo, la expresión auxiliar `H` de 6.91 tiene
un polo cuando `ka = (π/2)(0.124/0.67)²`. La formulación no debe ocultar
resultados no físicos de ese entorno mediante un ajuste de la curva.

## Datos publicados para comparación posterior

[Cuatro paredes de yeso con montantes metálicos](../validation/v7-hansen-steel-wall-octaves.json)
recoge los valores numéricos de las cuatro primeras filas de particiones de
yeso con acero de la tabla 7.13, p. 446. Son espectros por octavas de paredes
con dos hojas de 16 mm, cámaras de 45 o 86 mm, vacías o rellenas de fibra de
vidrio. Se conserva la distinción entre masa total declarada y masa de cada
hoja.

La publicación no da en esas filas todos los datos necesarios para reconstruir
el ensayo: faltan dimensiones de la muestra, sección y separación de montantes,
uniones, propiedades elásticas y pérdidas de las hojas, entre otros. Por ello:

- Los datos se incluyen como objetivos de comparación trazables.
- Una comparación que suponga los datos ausentes debe mostrar esas suposiciones.
- No se ajustan parámetros desconocidos para luego declarar validación
  independiente ni un margen universal de precisión.
- No se reconstruyen tercios de octava a partir de las octavas publicadas.

La mejora observada al rellenar la cámara varía con la frecuencia. También la
caída próxima a coincidencia difiere entre las muestras. Esto descarta usar una
corrección constante de varios dB para representar cualquier cámara absorbente.

## Qué falta para validar precisión experimental

Se necesita un ensayo con geometría, propiedades de hojas, montantes, tornillos,
relleno y condiciones de montaje documentadas, además de su espectro medido y
su incertidumbre. Los datos usados para identificar flexibilidades o pérdidas
deben separarse de los ensayos empleados para evaluar el error predictivo.
