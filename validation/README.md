# Banco de validación

Este directorio conserva evidencias de referencia independientes de las salidas
generadas por la aplicación. En la primera versión solo contiene casos analíticos:
**no hay mediciones experimentales ni curvas de INSUL**.

`cases.json` contiene nueve casos con entradas SI, resultado esperado, unidad,
derivación y tolerancia absoluta. Los valores se calcularon con expresiones
algebraicas reducidas y la biblioteca estándar `math`, sin importar el motor.
`data_status` los identifica como `analytical_not_experimental`. Estos casos
comprueban implementación numérica; no cuantifican error de predicción física.

Las pruebas de `tests/` complementan los ejemplos con límites, entradas imposibles,
integración numérica independiente y comparación de Rw con Phonometry. Desde la
raíz del repositorio:

```sh
uv sync --locked --all-extras
uv run pytest
```

La tolerancia numérica es específica de cada comprobación. No ampliar tolerancias
para ocultar una regresión; justificar el cambio de modelo o de aritmética y
actualizar de forma revisable la evidencia.

Para añadir mediciones reales se necesita fuente primaria, licencia, sistema y
montaje, unidades, bandas, método de ensayo, incertidumbre conocida y separación
entre casos de ajuste y evaluación. El formato deberá ampliarse de manera
versionada cuando exista el primer conjunto real; no almacenar como mediciones
los resultados del propio predictor.

Véanse el [plan científico](../docs/validation.md), las
[ecuaciones](../docs/theory.md) y el [registro de fuentes](../docs/sources.md).
