# Hoja de ruta

La versión **0.4.0** amplía la navegación por elementos y composiciones, conserva
variantes y añade cuatro hojas, gases, Facing y Porous al modelo ideal. La
prioridad científica sigue siendo determinar dónde ese modelo describe ensayos
reales. Los controles de funciones pendientes se identifican y no producen
resultados atribuidos a modelos que aún no existen.

| Área | Entrega V4 | Siguiente criterio de aceptación |
| --- | --- | --- |
| Motor | Una a cuatro hojas, flexión/pérdidas, gas ideal, Miki en cámara/Facing/lámina libre, bandas integradas | Revisar fuentes primarias y contrastar curvas experimentales reservadas |
| Experiencia de uso | Pestañas anidadas, productos integrados, espesor/cantidad, 3D rotatorio/2D, gráfica ajustable y comparación | Pruebas con consultores y ejecución nativa en Windows |
| Catálogo internacional | Siete familias XML10.0/8: 3242 entradas; compatibilidad 9.0/22; lectura ΔL con procedencia | Verificar propiedades y ensayos; ampliar datos públicos redistribuibles |
| Clasificación | Rw y STC32/8 provisionales; resumen energético por octavas | Revisión primaria ISO 717-1/ASTM E413 de edición aplicable; C/Ctr |
| Reproducción | Esquema 3 con composición activa y variantes, migración V1/V2, CLI e informes | Expedientes completos de validación y límites por familia |
| Distribución | Fuentes y paquete Python | Instalador Windows probado, inventario de licencias y actualización revisados |

## Modelos pendientes y criterios de aceptación

1. **Conexiones estructurales.** Montantes, separadores de vidrio, amarres y
   fijaciones necesitan rigidez dinámica y una ruta de transmisión validada.
   Los archivos Stud solo aportan dimensiones. La predicción se bloquea cuando
   la composición solicita ese acoplamiento.
2. **Gomperts y Mechel.** Recuperar los artículos completos, fijar geometría,
   impedancias de radiación, pérdidas, posición y sellado, y contrastar casos
   publicados antes de habilitar esos métodos. La abertura ideal por área sigue
   siendo una opción explícita distinta.
3. **Impacto y Floor Cover predicho.** Implementar excitación, movilidad y
   radiación del suelo; contrastar la mejora de revestimientos por base compatible.
   Mostrar un ΔL importado no aporta el Ln del suelo ni su clasificación.
4. **Ruido de lluvia.** Implementar fuerza de gotas, distribución de tamaños,
   respuesta/radiación de placa y diferencias de área entre lluvia natural y
   laboratorio. Documentar cada salida de potencia/intensidad/presión y validar
   antes de mostrar dBA de lluvia.
5. **Fenómenos de placa y ventana.** Evaluar tamaño finito, bordes, cortante en
   placas gruesas, ortotropía, perfiles y laminados viscoelásticos. El cambio de
   gas por sí solo no implementa el modelo modal de acristalamiento de INSUL.

## Evidencia experimental y alcance

Incorporar primero placas homogéneas y dobles hojas mecánicamente independientes,
con composición, propiedades, montaje e incertidumbre documentados. Definir dominio,
tolerancias y métricas antes de ajustar parámetros; separar calibración y evaluación
y publicar también los casos fallidos. Para Facing/Porous se necesitan propiedades
verificadas y mediciones apropiadas a la transmisión de láminas sin respaldo.

La conformidad de STC con una edición normativa, C/Ctr, IIC, Ln,w, L'nT,w y el aislamiento entre recintos ISO 12354 requieren
rutas de cálculo y normas específicas. La selección de Floor o Roof no convierte
TL aéreo en impacto o lluvia; esas excitaciones están bloqueadas mientras falten
sus modelos.

La guía INSUL y las capturas son referencias funcionales; los registros
[V2](v2-reference-review.md) y [V3](v3-reference-review.md) documentan qué se leyó.
Parecerse en controles o índices globales no demuestra equivalencia de motores.
Noiz no hereda los márgenes de error del About de INSUL.
