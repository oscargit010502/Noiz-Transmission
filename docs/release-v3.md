# Entrega V3 · 0.3.0

La V3 convierte el editor en un espacio de trabajo con variantes persistentes,
controles anidados y vistas de construcción. La distribución pública contiene
materiales sintéticos; el catálogo personal se distribuye por separado al usuario.

## Cambios disponibles

- Wall/Ceiling Single–Quad: cuatro hojas y tres Frames interiores como máximo.
- Seis Layer por Panel, Thickness editable, Quantity 1–10 y activación individual.
- Búsqueda, Category y Manufacturer en listas; seleccionar un producto adopta su
  espesor nominal sin perder las modificaciones de otras capas.
- Frame, Infill y cantidades cero; gas de cámara en Glazing.
- Facing, Leak, Floor cover, Rainfall y Porous con sus controles particulares.
- Vista 3D rotatoria y corte 2D, opacidad y espesores de componentes activos.
- Tabla en octavas, Chart/Tables en tercios, comparaciones y gráfica ajustable.
- Proyectos de esquema 3 que conservan las variantes inactivas y su procedencia.
- Matrices para hasta cuatro placas, gases ideales, Facing y lámina porosa Miki.
- Importación INSUL 10.0/8 de siete familias, incluido Stud; lectura de curvas ΔL.

Los controles Gomperts/Mechel, Stud, impacto y lluvia conservan parámetros, pero
sus modelos no están implementados. Esas configuraciones no producen una curva
sustitutiva. La fuga calculable es únicamente el modelo explícito de área abierta
ideal. No se atribuye a Noiz la precisión publicada para INSUL.

## Comprobaciones de esta entrega

Entorno Linux, Python 3.13.5, interfaz Qt offscreen:

| Comprobación | Resultado |
| --- | --- |
| `pytest -q -W error --tb=short` | 542 pruebas aprobadas, 72,32 s |
| `ruff check .` y `git diff --check` | Correctos |
| `uv sync --locked --all-extras --python 3.13` | Instalación reproducible con lockfile |
| `python -m build --installer uv` | Wheel y sdist 0.3.0 construidos |
| Wheel instalado fuera del checkout | Inicio Qt, cuatro referencias públicas, trabajador Single y 21 bandas; Rw 29 dB |
| CLI Single, Quad, Glazing y Porous | JSON, CSV e informe HTML generados |
| Interacción | F5/Ctrl+S incorporan texto pendiente; filtros, cambios de variante, guardado y reapertura verificados |
| Presentación | Captura pública de cálculo real; distribución revisada a 1480×940 y 1366×768; mínimo 1024×680 |

Resultados de los ejemplos sintéticos: Single 10 kg/m² y 12,5 mm, Rw provisional
29 dB; Quad 40 kg/m² y 350 mm, incidencia normal sin Rw; Glazing con argón 30 kg/m²
y 28 mm, normal sin Rw; Porous 50 mm, σ supuesto de 10.000 Pa·s/m², Rw provisional
7 dB y masa no inferida. Estos casos verifican la ejecución, no la precisión
experimental de un producto comercial.

Windows tiene un lanzador `.cmd` y CI configurada, pero no se verificó nativamente
en esta sesión. No hay instalador `.exe`. Véase [cómo probar en Windows](../PROBAR_EN_WINDOWS.md).

## Datos y procedencia

El catálogo personal reúne 3242 registros: Material 1575, Profile 281, Glazing 80,
Absorption 523, Floor Cover 669, Core 45 y Stud 69. De ellos, 1180 cumplen los
requisitos de datos para placa isotrópica; eso no acredita ensayos. Se conserva
SHA-256, identificador, campos originales y advertencias. La reparación de un
carácter de control en el nombre de un absorbente se registra explícitamente.

El ZIP personal contiene `local_data/catalog-v3.json` y
`local_data/v3_catalog_demo.noiz.json`. Los XML, catálogos privados y capturas con
nombres comerciales quedan fuera de Git, del ZIP público y del paquete Python.
La captura pública usa únicamente valores sintéticos MIT.
