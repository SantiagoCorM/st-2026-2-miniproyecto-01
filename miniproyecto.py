"""Miniproyecto 1: la serie del grupo, de las líneas base al mejor modelo clásico.

Se corre de principio a fin con

    python miniproyecto.py

y deja las figuras en figuras/ y la tabla en resultados/metricas.csv. Las
partes marcadas con TODO las completa el grupo; mientras falten, el guion las
reporta como pendientes y sigue. El informe, docs/informe.md, cita las cifras
y las figuras que produce este guion.
"""
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from comun import (RAIZ, backtest, cargar_serie, estacional_ingenuo,  # noqa: E402
                   fechas_siguientes, ingenuo)

warnings.filterwarnings("ignore")
FIGURAS = RAIZ / "figuras"
RESULTADOS = RAIZ / "resultados"
FIGURAS.mkdir(exist_ok=True)
RESULTADOS.mkdir(exist_ok=True)

# ============================================================
# 1. La serie
# ============================================================
# Cambie estos cuatro datos por los de la serie del grupo y documente la
# fuente en datos/README.md. La serie de ejemplo solo sirve para probar que
# el guion corre.
ARCHIVO = "datos/precipitacion_florencia.csv"
FECHA = "Month"
VALOR = "PRECTOTCORR"
PERIODO = 12

# Lo que se hizo con los huecos y con los datos atípicos, en una línea. Va
# a la columna `decision` de la tabla de métricas.
DECISION = "No se identificaron valores faltantes. Se detectaron 5 posibles valores atípicos mediante IQR, pero se conservaron por no existir evidencia de errores de medición."

def preparar(serie):
    """Prepara la serie conservando los valores originales.

    No se identificaron valores faltantes en la descarga.
    Los posibles valores extremos se conservarán inicialmente,
    hasta evaluar si corresponden a eventos reales o errores.
    """
    serie = serie.copy()

    assert serie.notna().all(), "La serie contiene valores faltantes."

    return serie


def graficar_serie(serie):
    figura, eje = plt.subplots(figsize=(9, 3.4))
    eje.plot(serie.index, serie.to_numpy())
    eje.set_title(f"{VALOR}: serie mensual")
    eje.set_ylabel(VALOR)
    figura.tight_layout()
    figura.savefig(FIGURAS / "serie.png", dpi=120)
    plt.close(figura)


# ============================================================
# 2. Descomposición
# ============================================================

def descomponer(serie):
    """Descomposición STL robusta con periodo de 12 meses."""

    from statsmodels.tsa.seasonal import STL

    resultado = STL(
        serie,
        period=PERIODO,
        robust=True
    ).fit()

    fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)

    axes[0].plot(serie)
    axes[0].set_title("Serie original")
    axes[0].set_ylabel("mm/día")

    axes[1].plot(resultado.trend)
    axes[1].set_title("Tendencia")
    axes[1].set_ylabel("mm/día")

    axes[2].plot(resultado.seasonal)
    axes[2].set_title("Componente estacional")
    axes[2].set_ylabel("mm/día")

    axes[3].plot(resultado.resid)
    axes[3].set_title("Residuo")
    axes[3].set_ylabel("mm/día")

    plt.tight_layout()
    plt.savefig("figuras/stl.png", dpi=300, bbox_inches="tight")
    plt.close()

    return resultado


# ============================================================
# 3. Estacionariedad e identificación
# ============================================================

def estacionariedad(serie):
    """Evalúa estacionariedad mediante ADF e identifica d y D."""

    from statsmodels.tsa.stattools import adfuller
    from statsmodels.graphics.tsaplots import plot_acf, plot_pacf

    # Cuatro versiones de la serie
    versiones = {
        "Original": serie,
        "Diferencia regular": serie.diff().dropna(),
        "Diferencia estacional": serie.diff(PERIODO).dropna(),
        "Regular + estacional": serie.diff().diff(PERIODO).dropna()
    }

    print("\nPRUEBAS DE ESTACIONARIEDAD ADF")
    print("-" * 55)

    resultados = {}

    for nombre, datos in versiones.items():
        prueba = adfuller(datos, regression="c", autolag="AIC")
        estadistico = prueba[0]
        pvalor = prueba[1]

        resultados[nombre] = pvalor

        print(f"{nombre}:")
        print(f"  Estadístico ADF: {estadistico:.4f}")
        print(f"  Valor p: {pvalor:.6f}")
        print(f"  Resultado: {'Estacionaria' if pvalor < 0.05 else 'No estacionaria'}")

    # Selección inicial de diferenciación:
    # se busca la combinación más sencilla que alcance p < 0.05.
    candidatos = [
        (0, 0, "Original"),
        (1, 0, "Diferencia regular"),
        (0, 1, "Diferencia estacional"),
        (1, 1, "Regular + estacional")
    ]

    elegidos = [
        (d, D, nombre)
        for d, D, nombre in candidatos
        if resultados[nombre] < 0.05
    ]

    if not elegidos:
        raise ValueError(
            "Ninguna versión alcanzó estacionariedad según ADF."
        )

    # En caso de empate, se prioriza la diferenciación estacional.
    d, D, nombre = min(
        elegidos,
        key=lambda x: (x[0] + x[1], -x[1])
    )

    print("\nDECISIÓN INICIAL")
    print(f"Serie seleccionada: {nombre}")
    print(f"d = {d}")
    print(f"D = {D}")

    # Aplicar las diferencias seleccionadas
    seleccionada = serie.copy()

    if d == 1:
        seleccionada = seleccionada.diff()

    if D == 1:
        seleccionada = seleccionada.diff(PERIODO)

    seleccionada = seleccionada.dropna()

    # ACF y PACF
    fig, axes = plt.subplots(2, 1, figsize=(12, 8))

    plot_acf(seleccionada, lags=36, ax=axes[0])
    axes[0].set_title("Función de autocorrelación (ACF)")

    plot_pacf(seleccionada, lags=36, method="ywm", ax=axes[1])
    axes[1].set_title("Función de autocorrelación parcial (PACF)")

    plt.tight_layout()
    plt.savefig("figuras/acf_pacf.png", dpi=300, bbox_inches="tight")
    plt.close()

    return d, D


# ============================================================
# 4. Modelos clásicos
# ============================================================
# Cada modelo es una función modelo(entrenamiento, h) que devuelve h
# pronósticos y solo usa `entrenamiento`. Así entra al backtest común.

def elegir_sarima(serie, d, D):
    """Selecciona SARIMA mediante AIC y evalúa sus residuos."""
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    from statsmodels.stats.diagnostic import acorr_ljungbox
    import itertools

    resultados = []

    # Rejilla pequeña: p, q, P y Q entre 0 y 1.
    combinaciones = list(itertools.product([0, 1], repeat=4))

    for p, q, P, Q in combinaciones:
        orden = (p, d, q)
        orden_estacional = (P, D, Q, PERIODO)

        try:
            ajuste = SARIMAX(
                serie,
                order=orden,
                seasonal_order=orden_estacional,
                enforce_stationarity=False,
                enforce_invertibility=False
            ).fit(disp=False, maxiter=200)

            resultados.append({
                "orden": orden,
                "orden_estacional": orden_estacional,
                "AIC": ajuste.aic
            })

        except Exception as error:
            print(f"Modelo {orden} x {orden_estacional} no ajustado: {error}")

    if not resultados:
        raise ValueError("No fue posible ajustar ningún modelo SARIMA.")

    tabla = pd.DataFrame(resultados).sort_values("AIC")

    print("\nCOMPARACIÓN DE MODELOS SARIMA")
    print(tabla.to_string(index=False))

    mejor = tabla.iloc[0]
    orden = mejor["orden"]
    orden_estacional = mejor["orden_estacional"]

    print("\nMEJOR MODELO SARIMA")
    print(f"Orden: {orden}")
    print(f"Orden estacional: {orden_estacional}")
    print(f"AIC: {mejor['AIC']:.4f}")

    # Ajustar el mejor modelo para analizar sus residuos.
    ajuste = SARIMAX(
        serie,
        order=orden,
        seasonal_order=orden_estacional,
        enforce_stationarity=False,
        enforce_invertibility=False
    ).fit(disp=False, maxiter=200)

    residuos = ajuste.resid.dropna()

    print("\nPRUEBA DE LJUNG-BOX")
    ljung_box = acorr_ljungbox(
        residuos,
        lags=[12, 24],
        return_df=True
    )
    print(ljung_box)

    fig, axes = plt.subplots(2, 1, figsize=(12, 8))

    axes[0].plot(residuos)
    axes[0].set_title("Residuos del mejor modelo SARIMA")
    axes[0].set_ylabel("Residuo")

    axes[1].hist(residuos, bins=30)
    axes[1].set_title("Distribución de los residuos")
    axes[1].set_xlabel("Residuo")

    plt.tight_layout()
    plt.savefig("figuras/residuos.png", dpi=300, bbox_inches="tight")
    plt.close()

    return orden, orden_estacional


def modelo_sarima(orden, orden_estacional):
    """Devuelve un modelo SARIMA compatible con el backtest."""
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    def modelo(entrenamiento, h):
        ajuste = SARIMAX(
            entrenamiento,
            order=orden,
            seasonal_order=orden_estacional,
            enforce_stationarity=False,
            enforce_invertibility=False
        ).fit(disp=False, maxiter=200)

        pronostico = ajuste.forecast(steps=h)
        return pronostico.to_numpy()

    return modelo


def exogenas(serie):
    """Genera variables exógenas conocidas para cada mes."""
    fechas = pd.date_range(
        start=serie.index.min(),
        end=serie.index.max() + pd.DateOffset(months=12),
        freq="MS"
    )

    x = pd.DataFrame(index=fechas)
    x["dias_mes"] = x.index.days_in_month

    return x


def modelo_sarimax(orden, orden_estacional, x):
    """Devuelve un modelo SARIMAX compatible con el backtest."""
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    def modelo(entrenamiento, h):
        fechas_futuras = fechas_siguientes(entrenamiento, h)

        x_entrenamiento = x.loc[entrenamiento.index]
        x_futuro = x.loc[fechas_futuras]

        ajuste = SARIMAX(
            entrenamiento,
            exog=x_entrenamiento,
            order=orden,
            seasonal_order=orden_estacional,
            enforce_stationarity=False,
            enforce_invertibility=False
        ).fit(disp=False, maxiter=200)

        pronostico = ajuste.get_forecast(
            steps=h,
            exog=x_futuro
        ).predicted_mean

        return pronostico.to_numpy()

    return modelo


# ============================================================
# 5. La tabla de métricas
# ============================================================

def fila(nombre, serie, modelo):
    _, promedio = backtest(serie, modelo)
    return {"modelo": nombre, "decision": DECISION,
            "RMSE": round(promedio["RMSE"], 2), "MAE": round(promedio["MAE"], 2),
            "MAPE": round(promedio["MAPE"], 2)}


def pendiente(parte, error):
    print(f"  pendiente: {parte} ({error})")


def main():
    cruda = cargar_serie(ARCHIVO, FECHA, VALOR)
    print(f"Serie: {len(cruda)} meses, de {cruda.index[0]:%Y-%m} a "
          f"{cruda.index[-1]:%Y-%m}, {cruda.isna().sum()} vacíos")
    serie = preparar(cruda)
    graficar_serie(serie)

    filas = [fila("ingenuo", serie, ingenuo),
             fila("estacional ingenuo", serie,
                  lambda t, h: estacional_ingenuo(t, h, PERIODO))]

    try:
        descomponer(serie)
    except NotImplementedError as error:
        pendiente("parte 2", error)

    try:
        d, D = estacionariedad(serie)
    except NotImplementedError as error:
        pendiente("parte 3", error)
        d = D = None

    if d is not None:
        try:
            orden, estacional = elegir_sarima(serie, d, D)
            filas.append(fila(f"SARIMA{orden}{estacional}", serie,
                              modelo_sarima(orden, estacional)))
            x = exogenas(serie)
            filas.append(fila(f"SARIMAX{orden}{estacional} + exógenas", serie,
                              modelo_sarimax(orden, estacional, x)))
        except NotImplementedError as error:
            pendiente("parte 4", error)

    tabla = pd.DataFrame(filas).sort_values("RMSE")
    tabla.to_csv(RESULTADOS / "metricas.csv", index=False)
    print(tabla.drop(columns="decision").to_string(index=False))
    print("Mejor modelo por RMSE:", tabla.iloc[0]["modelo"])


if __name__ == "__main__":
    main()
