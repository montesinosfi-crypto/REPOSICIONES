import streamlit as st
import pandas as pd
import os
import psycopg2
from psycopg2.extras import RealDictCursor

st.set_page_config(page_title="Panel de Inventario - Resurtido", page_icon="📦", layout="wide")
st.title("📦 Panel de Inventario y Resurtido")
st.caption("Datos desde PostgreSQL | Almacén central: CEDIS Vallejo")

CLASIFICACION = {
    "AAA": ["BOUTIQUE TLALNEPANTLA", "SHOPIFY"],
    "AA": ["BOUTIQUE CENTRO MEDICO", "BOUTIQUE ROMA", "BOUTIQUE POLANCO", "BOUTIQUE PEDREGAL",
           "BOUTIQUE LA RAZA", "BOUTIQUE HOSPITAL GENERAL", "BOUTIQUE GUADALAJARA", "BOUTIQUE LEON",
           "BOUTIQUE MONTERREY", "BOUTIQUE OAXACA", "BOUTIQUE TOLUCA", "BOUTIQUE VILLAHERMOSA",
           "BOUTIQUE LINDAVISTA", "BOUTIQUE RENATO LEDUC"],
    "A": ["BOUTIQUE CONDESA", "BOUTIQUE SALTILLO"]
}
MAXIMOS = {
    "AAA": {"XS": 5, "S": 5, "M": 5, "L": 3, "XL": 2, "XXL": 1},
    "AA":  {"XS": 3, "S": 3, "M": 3, "L": 2, "XL": 1, "XXL": 1},
    "A":   {"XS": 1, "S": 1, "M": 1, "L": 1, "XL": 1, "XXL": 1},
}
ORDEN_TALLA = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL"]

def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        st.error("No se encontró DATABASE_URL.")
        st.stop()
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(database_url, cursor_factory=RealDictCursor)

@st.cache_data(ttl=300)
def load_data():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM productos", conn)
    conn.close()
    return df

@st.cache_data(ttl=300)
def load_stock_boutiques():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM stock_boutiques", conn)
    conn.close()
    return df

def get_clasificacion(sucursal):
    for clasif, lista in CLASIFICACION.items():
        if sucursal in lista:
            return clasif
    return "A"

def get_maximo(sku, nombre, talla, clasificacion):
    talla = str(talla).strip().upper()
    sku_up = str(sku).upper()
    nombre_up = str(nombre).upper()
    if sku_up.startswith("GOQUI"):
        return 6 if clasificacion != "A" else 3
    if "FILIPINA" in nombre_up and "ECO" not in nombre_up and "ECO" not in sku_up:
        return 1
    return MAXIMOS.get(clasificacion, {}).get(talla, 1)

try:
    df_base = load_data()
    stock_bout = load_stock_boutiques()
except Exception as e:
    st.error(f"Error conectando a la base: {e}")
    st.stop()

st.sidebar.header("Filtros")
todas_boutiques = sorted(stock_bout["sucursal"].unique().tolist()) if not stock_bout.empty else []
boutique_sel = st.sidebar.selectbox("Boutique", ["Todas"] + todas_boutiques)
colecciones = ["Todas"] + sorted(df_base["coleccion"].dropna().unique().tolist())
coleccion_sel = st.sidebar.selectbox("Colección", colecciones)
familias = ["Todas"] + sorted(df_base["familia"].dropna().unique().tolist())
familia_sel = st.sidebar.selectbox("Familia", familias)
buscar = st.sidebar.text_input("Buscar")
vista = st.sidebar.radio("Vista", ["Matriz de inventario", "Agrupada por producto", "Resurtido por boutique", "Detalle por SKU"])

df_filt = df_base.copy()
if coleccion_sel != "Todas":
    df_filt = df_filt[df_filt["coleccion"] == coleccion_sel]
if familia_sel != "Todas":
    df_filt = df_filt[df_filt["familia"] == familia_sel]
if buscar:
    mask = df_filt["sku"].str.contains(buscar, case=False, na=False) | \
           df_filt["linea"].fillna("").str.contains(buscar, case=False, na=False)
    df_filt = df_filt[mask]

c1, c2 = st.columns(2)
c1.metric("SKUs filtrados", len(df_filt))
c2.metric("Con stock CEDIS", int((df_filt["stock_cedis"] > 0).sum()))
st.divider()

if vista == "Matriz de inventario":
    st.subheader("Matriz de inventario por sucursal")
    if not stock_bout.empty:
        df_m = df_filt.merge(stock_bout, on="sku", how="left")
        df_m["stock"] = df_m["stock"].fillna(0).astype(int)
        pivot = df_m.pivot_table(
            index=["linea", "coleccion", "color", "talla"],
            columns="sucursal",
            values="stock",
            aggfunc="sum",
            fill_value=0
        ).reset_index()
        pivot["talla_ord"] = pivot["talla"].map({t: i for i, t in enumerate(ORDEN_TALLA)}).fillna(99)
        pivot = pivot.sort_values(["linea", "color", "talla_ord"]).drop(columns=["talla_ord"])
        st.dataframe(pivot, use_container_width=True, hide_index=True)
    else:
        st.warning("No hay stock de boutiques.")

elif vista == "Agrupada por producto":
    st.subheader("Productos agrupados")
    if boutique_sel == "Todas":
        st.info("Selecciona una boutique.")
    else:
        clasif = get_clasificacion(boutique_sel)
        st.write(f"**Boutique:** {boutique_sel} | **Clasificación:** {clasif}")
        maximos_txt = " | ".join([f"{t}={m}" for t, m in MAXIMOS[clasif].items()])
        st.caption(f"Máximos {clasif}: {maximos_txt}")

        stock_esta = stock_bout[stock_bout["sucursal"] == boutique_sel][["sku", "stock"]].rename(columns={"stock": "stock_boutique"})
        df_b = df_filt.merge(stock_esta, on="sku", how="left")
        df_b["stock_boutique"] = df_b["stock_boutique"].fillna(0).astype(int)
        df_b["maximo"] = df_b.apply(lambda r: get_maximo(r["sku"], r["nombre"], r["talla"], clasif), axis=1)
        df_b["necesidad"] = (df_b["maximo"] - df_b["stock_boutique"]).clip(lower=0)
        df_b["resurtido"] = df_b[["necesidad", "stock_cedis"]].min(axis=1).astype(int)

        for linea, grupo in df_b.groupby("linea"):
            with st.container():
                st.markdown(f"### {linea}")
                st.caption(f"Colección: {grupo['coleccion'].iloc[0]} | Familia: {grupo['familia'].iloc[0]}")
                st.write(f"Sucursal: **{int(grupo['stock_boutique'].sum())}** | CEDIS: **{int(grupo['stock_cedis'].sum())}**")
                vars_df = grupo[["sku", "color", "talla", "stock_boutique", "stock_cedis", "maximo", "resurtido"]].copy()
                vars_df["talla_ord"] = vars_df["talla"].map({t: i for i, t in enumerate(ORDEN_TALLA)}).fillna(99)
                vars_df = vars_df.sort_values(["color", "talla_ord"]).drop(columns=["talla_ord"])
                st.dataframe(vars_df, hide_index=True, use_container_width=True)
                st.divider()

elif vista == "Resurtido por boutique":
    st.subheader("Resurtido sugerido")
    if boutique_sel == "Todas":
        st.info("Selecciona una boutique.")
    else:
        clasif = get_clasificacion(boutique_sel)
        st.write(f"**Clasificación:** {clasif}")
        stock_esta = stock_bout[stock_bout["sucursal"] == boutique_sel][["sku", "stock"]].rename(columns={"stock": "stock_boutique"})
        df_b = df_filt.merge(stock_esta, on="sku", how="left")
        df_b["stock_boutique"] = df_b["stock_boutique"].fillna(0).astype(int)
        df_b["maximo"] = df_b.apply(lambda r: get_maximo(r["sku"], r["nombre"], r["talla"], clasif), axis=1)
        df_b["necesidad"] = (df_b["maximo"] - df_b["stock_boutique"]).clip(lower=0)
        df_b["resurtido"] = df_b[["necesidad", "stock_cedis"]].min(axis=1).astype(int)
        mostrar = df_b[df_b["necesidad"] > 0]
        if mostrar.empty:
            st.success("Al máximo.")
        else:
            st.metric("Piezas a resurtir", int(mostrar["resurtido"].sum()))
            st.dataframe(mostrar[["sku", "linea", "coleccion", "color", "talla", "stock_boutique", "maximo", "resurtido", "stock_cedis"]],
                         use_container_width=True, hide_index=True)

else:
    st.subheader("Detalle por SKU")
    st.dataframe(df_filt[["sku", "linea", "coleccion", "familia", "color", "talla", "stock_cedis"]],
                 use_container_width=True, hide_index=True)

st.divider()
st.caption("Datos desde PostgreSQL. Actualiza existencias ejecutando load_data.py")
