#!/usr/bin/env bash
# Descarga los datos abiertos de BiciMAD (datos.madrid.es + EMT + feed GBFS en vivo).
set -euo pipefail
cd "$(dirname "$0")/data"

echo "Estaciones (GeoJSON estático EMT)..."
curl -sL "https://datos.emtmadrid.es/dataset/5fcc0945-2cbd-46c3-801a-6a83f4167c11/resource/105ce5df-793f-4e0a-a88e-5d3b3f024a5d/download/bikestationbicimad_geojson.json" -o stations.geojson

echo "Viajes diarios desde 2024 (datos.madrid.es)..."
curl -sL "https://datos.madrid.es/dataset/900043-0-viajes-diario-bicimad/resource/900043-0-viajes-diario-bicimad-csv/download/900043-0-viajes-diario-bicimad-csv" -o viajes_diarios.csv

echo "Usuarios activos mensuales (EMT)..."
curl -sL "https://datos.emtmadrid.es/dataset/94367cbb-e8ef-4b16-8919-9101f4fc806b/resource/7df58d15-da12-420d-9881-97e54de762c4/download/historicousuariosactivos.csv" -o usuarios_activos.csv

echo "GBFS en vivo (station_information + station_status)..."
curl -sL "https://madrid.publicbikesystem.net/customer/gbfs/v2/en/station_information" -o station_information.json
curl -sL "https://madrid.publicbikesystem.net/customer/gbfs/v2/en/station_status" -o station_status.json

echo "Distritos de Madrid (geoportal)..."
curl -sL "https://geoportal.madrid.es/fsdescargas/IDEAM_WBGEOPORTAL/LIMITES_ADMINISTRATIVOS/Distritos/TopoJSON/Distritos.json" -o distritos.topojson

if [ ! -f bicimad_2022.zip ]; then
  echo "Microdatos de viajes 2022 (~315 MB, solo la primera vez)..."
  curl -L "https://media.emtmadrid.es/-uHaW6iZkhG" -o bicimad_2022.zip
fi

echo "OK. Ahora ejecuta: python3 build.py"
