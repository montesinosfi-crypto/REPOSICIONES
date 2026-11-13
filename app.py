import streamlit as st
import pandas as pd
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
import re

st.set_page_config(page_title="Panel de Inventario - Resurtido", page_icon="📦", layout="wide")
st.title("📦 Panel de Inventario y Resurtido")
st.caption("Datos desde PostgreSQL | Imágenes y visibilidad desde gallantdale.com")

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

def normalize(text):
    if pd.isna(text):
        return ""
    return re.sub(r'[^A-Z0-9]', '', str(text).upper())

@st.cache_data(ttl=3600)
def fetch_shopify_catalog():
    base = "https://gallantdale.com/products.json"
    all_variants = []
    page = 1
    while page <= 25:
        try:
            r = requests.get(f"{base}?limit=250&page={page}", timeout=30)
            if r.status_code != 200:
                break
            products = r.json().get("products", [])
            if not products:
                break
            for p in products:
                image = p["images"][0]["src"] if p.get("images") else None
                title = p.get("title", "")
                for v in p.get("variants", []):
                    sku = str(v.get("sku") or "").strip()
                    all_variants.append({
                        "sku": sku,
                        "title_norm": normalize(title),
                        "image_src": image,
                        "visible_web": True,
                    })
            if len(products) < 250:
                break
            page += 1
        except Exception as e:
            st.warning(f"Error catálogo: {e}")
            break
    return pd.DataFrame(all_variants) if all_variants else pd.DataFrame(columns=["sku", "title_norm", "image_src", "visible_web"])

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

# Carga principal
try:
    df_base = load_data()
    stock_bout = load_stock_boutiques()
except Exception as e:
    st.error(f"Error conectando a la base: {e}")
    st.stop()

# Intentar traer catálogo (no crítico)
df_base["image_src"] = None
df_base["visible_web"] = False
try:
    with st.spinner("Cargando imágenes desde gallantdale.com..."):
        df_shop = fetch_shopify_catalog()
    if not df_shop.empty:
        # Match por SKU
        sku_map = df_shop[df_shop["sku"] != ""].drop_duplicates("sku")[["sku", "image_src", "visible_web"]]
        df_base = df_base.merge(sku_map, on="sku", how="left", suffixes=("", "_shop"))
        df_base["image_src"] = df_base["image_src"].fillna(df_base.get("image_src_shop"))
        df_base["visible_web"] = df_base["visible_web"].fillna(df_base.get("visible_web_shop", False))
        df_base = df_base.drop(columns=[c for c in df_base.columns if c.endswith("_shop")], errors="ignore")

        # Match por nombre para los que no tienen imagen
        df_base["linea_norm"] = df_base["linea"].apply(normalize)
        title_map = df_shop.drop_duplicates("title_norm")[["title_norm", "image_src"]].rename(columns={"image_src": "img_title"})
        df_base = df_base.merge(title_map, left_on="linea_norm", right_on="title_norm", how="left")
        df_base["image_src"] = df_base["image_src"].fillna(df_base["img_title"])
        df_base = df_base.drop(columns=["linea_norm", "title_norm", "img_title"], errors="ignore")
except Exception as e:
    st.warning(f"No se pudieron cargar imágenes: {e}")

df_base["visible_web"] = df_base["visible_web"].fillna(False)
df_base["image_src"] = df_base["image_src"].fillna("")

# Sidebar
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

c1, c2, c3 = st.columns(3)
c1.metric("SKUs filtrados", len(df_filt))
c2.metric("Publicados en web", int(df_filt["visible_web"].sum()))
c3.metric("Con imagen", int((df_filt["image_src"] != "").sum()))
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
            imgs = grupo["image_src"].dropna()
            img = imgs.iloc[0] if len(imgs) > 0 and imgs.iloc[0] != "" else None
            publicado = int(grupo["visible_web"].sum())
            with st.container():
                c1, c2 = st.columns([1, 3])
                with c1:
                    if img:
                        st.image(img, use_container_width=True)
                    else:
                        st.info("Sin imagen")
                with c2:
                    st.markdown(f"### {linea}")
                    st.caption(f"Colección: {grupo['coleccion'].iloc[0]} | Familia: {grupo['familia'].iloc[0]}")
                    if publicado == 0:
                        st.error("⚠️ Ninguna variante publicada en la web")
                    elif publicado < len(grupo):
                        st.warning(f"{publicado}/{len(grupo)} variantes publicadas")
                    else:
                        st.success("Todas las variantes publicadas")
                    st.write(f"Sucursal: **{int(grupo['stock_boutique'].sum())}** | CEDIS: **{int(grupo['stock_cedis'].sum())}**")
                    vars_df = grupo[["sku", "color", "talla", "stock_boutique", "stock_cedis", "maximo", "resurtido", "visible_web"]].copy()
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
            st.dataframe(mostrar[["sku", "linea", "coleccion", "color", "talla", "stock_boutique", "maximo", "resurtido", "stock_cedis", "visible_web"]],
                         use_container_width=True, hide_index=True)

else:
    st.subheader("Detalle por SKU")
    st.dataframe(df_filt[["sku", "linea", "coleccion", "familia", "color", "talla", "stock_cedis", "visible_web"]],
                 use_container_width=True, hide_index=True)

st.divider()
st.caption("Imágenes por SKU o por nombre | Visibilidad desde gallantdale.com")
