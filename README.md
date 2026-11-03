# bicimad-viz

Dashboard de los datos abiertos de BiciMAD (servicio público de bicicleta eléctrica de Madrid).

Abre `web/index.html` en el navegador, sin servidor ni dependencias. Se adapta a modo claro/oscuro del sistema.

## Qué muestra

- **KPIs**: estaciones en servicio, bicis disponibles ahora, viajes del año, día récord, usuarios activos.
- **Mapa de estaciones** sobre los distritos de Madrid: cada punto es una estación (tamaño = capacidad, color = % de bicis disponibles en el momento del snapshot GBFS).
- **Cómo se mueve la ciudad**: mapa animado con slider horario (y play). Tamaño = movimientos por hora, color divergente rojo (salen bicis) ↔ azul (llegan). Calculado con los 4,1 M de microdatos de viajes de 2022, el último año publicado, separando laborables de fin de semana.
- **Viajes por día** (feb 2024 – hoy) con media móvil de 7 días.
- **Comparativa mensual** 2024 frente a 2025.
- **Media por día de la semana** y **heatmap mes × día**.
- **Usuarios activos mensuales**.

Cada tarjeta tiene un botón «Datos» con la tabla completa, y tooltips al pasar el ratón.

## Actualizar los datos

```bash
./fetch_data.sh     # descarga datos crudos a data/
python3 build.py    # regenera web/data.js
```

## Fuentes

| Dato | Origen |
|---|---|
| Viajes diarios desde 2024 | [datos.madrid.es](https://datos.madrid.es/portal/site/egob) — «Bicimad. Histórico de total viajes por día desde 2024» |
| Usuarios activos mensuales | datos.emtmadrid.es — «Usuarios de bicimad activos» |
| Estaciones (estático) | datos.emtmadrid.es — «Estaciones de Bicimad» (GeoJSON) |
| Disponibilidad en vivo | Feed GBFS: `madrid.publicbikesystem.net/customer/gbfs/v2/gbfs.json` |
| Microdatos de viajes 2022 | datos.madrid.es — «Históricos de Bicimad (2017-2023)», ZIP anual de media.emtmadrid.es |
| Distritos (fondo del mapa) | geoportal.madrid.es — «Límites administrativos», TopoJSON |

Solo Python 3 (stdlib) y `curl`. El dashboard es HTML+SVG vanilla, sin librerías.
