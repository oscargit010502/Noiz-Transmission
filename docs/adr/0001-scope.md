# ADR 0001 — Elementos constructivos y modelos verificables

Fecha: 2026-10-13. Estado: adoptada para la primera implementación.

## Contexto

El producto aspira a ofrecer a consultores acústicos una alternativa abierta para
diseñar elementos aislantes. INSUL 10 constituye una referencia funcional indicada
por el usuario, pero la amplitud de una interfaz comercial no prueba que un motor
nuevo cubra sus modelos ni alcance su precisión.

## Decisión

Se separan motor físico, biblioteca, interfaz, banco de validación y documentación.
Se usa Python, NumPy/SciPy y PySide6. Phonometry se utiliza como dependencia opcional
de comparación de clasificación, fijada a una versión reproducible.

El primer modelo es la ley de masas de un panel homogéneo ideal, con incidencia
normal o difusa de ángulo máximo explícito. La frecuencia crítica y la resonancia
masa–aire–masa se calculan como diagnósticos independientes. No se implementa una
curva multicapa sin modelo documentado y verificado.

El catálogo se plantea internacional y empieza con datos sintéticos identificados.
No se incorporan marcas ni precisión comercial sin procedencia comprobable. Rw
permanece provisional hasta una revisión normativa independiente.

Se modelan elementos, no edificios ni aislamiento entre recintos. ISO 12354,
transmisión lateral y uniones se consideran una ampliación posterior. STC, IIC,
Ln,w y L'nT,w requieren alcances y validaciones específicos.

## Consecuencias

Es posible verificar pronto las ecuaciones y reproducir resultados con un alcance
pequeño. Las gráficas de ley de masas no deben presentarse como predicciones
validadas de elementos comerciales reales. El primer hito es una base funcional
de investigación; la aptitud para consultoría depende de superar las fases
experimentales del [plan de validación](../validation.md).

El código propio mantiene la licencia MIT existente. La implementación no copia
la interfaz, manual, base de datos ni código de INSUL. Documentar referencias
funcionales no implica afiliación, compatibilidad ni certificación.
