import requests
import pandas as pd

# Coordenadas aproximadas de Florencia, Caquetá
LATITUD = 1.6144
LONGITUD = -75.6062

# Configuración de NASA POWER
URL = "https://power.larc.nasa.gov/api/temporal/monthly/point"

PARAMETROS = {
    "parameters": "PRECTOTCORR",
    "community": "AG",
    "longitude": LONGITUD,
    "latitude": LATITUD,
    "start": 2001,
    "end": 2025,
    "format": "JSON"
}

print("Consultando NASA POWER...")

respuesta = requests.get(URL, params=PARAMETROS, timeout=60)
respuesta.raise_for_status()

datos = respuesta.json()

# Extraer la variable meteorológica
valores = datos["properties"]["parameter"]["PRECTOTCORR"]

# Crear DataFrame
serie = pd.DataFrame(
    list(valores.items()),
    columns=["Month", "PRECTOTCORR"]
)

# Convertir fechas y valores
serie["Month"] = serie["Month"].astype(str)
serie = serie[serie["Month"].str[-2:].astype(int).between(1, 12)].copy()
serie["Month"] = pd.to_datetime(serie["Month"], format="%Y%m")
serie["PRECTOTCORR"] = pd.to_numeric(
    serie["PRECTOTCORR"], errors="coerce"
)

# Ordenar cronológicamente
serie = serie.sort_values("Month").reset_index(drop=True)

# Guardar CSV
ruta = "datos/precipitacion_florencia.csv"
serie.to_csv(ruta, index=False)

print("\nDescarga completada.")
print("Archivo:", ruta)
print("Observaciones:", len(serie))
print("Primer mes:", serie["Month"].min())
print("Último mes:", serie["Month"].max())
print("Valores faltantes:", serie["PRECTOTCORR"].isna().sum())
print("\nPrimeros registros:")
print(serie.head())