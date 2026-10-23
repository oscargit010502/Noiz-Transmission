# Documentación técnica

Noiz Transmission **0.6.0** permite editar hasta cuatro hojas, conservar variantes,
importar ocho familias XML —incluidas conexiones— y calcular transmisión aérea ideal de placas,
cámaras con gas y materiales porosos. Incluye Facing, vista 3D rotatoria, corte 2D
y resumen por octavas. Impacto, lluvia, conexiones estructurales y Gomperts/Mechel
conservan configuración pero todavía no disponen de predicción. La precisión
experimental de sistemas comerciales sigue pendiente de evaluación.

V5.1 incluye un catálogo integrado de 3.629 registros y mejora la representación
con proporciones reales, recorte y detalle opcionales. La gráfica tiene área
cuadrada, leyenda a la derecha y el contorno ajustado de referencia Rw o STC.
V6 añade la aproximación angular de tamaño finito, pérdidas adicionales de borde,
optimización del motor y esquema 4 de proyectos. Las limitaciones de modos finitos,
uniones y precisión experimental se documentan por separado.

- [Entrega V6 y cómo probarla](release-v6.md).
- [Física V6: tamaño finito, rigidez y pérdidas](v6-physics.md).
- [Revisión de Hansen, Vér/Beranek y Barron](v6-reference-review.md).
- [Evidencia y límites de validación V6](v6-evidence.md).
- [Rendimiento V6 y procedimiento reproducible](../validation/v6-performance.md).

- [Arquitectura y cinco componentes](architecture.md).
- [Ecuaciones, bandas, supuestos y límites V1–V4](theory.md).
- [Catálogo internacional, XML y procedencia](materials.md).
- [Catálogo nativo: distribución y carga automática 0.5.1](catalog-native.md).
- [Verificación y plan de validación científica](validation.md).
- [Instalación, CLI y reproducción](reproducibility.md).
- [Hoja de ruta y criterios de aceptación](roadmap.md).
- [Fuentes consultadas y lecturas pendientes](sources.md).
- [Revisión de guía INSUL, capturas, folleto y requisitos v2](v2-reference-review.md).
- [Revisión de controles, límites físicos y fuentes V3](v3-reference-review.md).
- [ADR 0001: decisión histórica de alcance v1](adr/0001-scope.md).
- [Banco de casos analíticos](../validation/README.md).

- [Entrega V4: interfaz compacta, visualización y comprobaciones](release-v4.md).
- [Selector Rw/STC y alcance de los índices de impacto](v4-ratings.md).
- [Entrega V5: geometría, catálogo y presentación de resultados](release-v5.md).
- [Geometría y procedencia V5: cotas XML y fuentes comprobadas](v5-geometry-sources.md).
