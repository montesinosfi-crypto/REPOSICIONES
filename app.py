import streamlit as st
import pandas as pd
import requests
import os
import re

st.set_page_config(page_title="Panel de Inventario - Piloto Shopify", page_icon="📦", layout="wide")
st.title("📦 Panel de Inventario - Piloto Shopify")
st.caption("Canal: Shopify (gallantdale.com) | Almacén que surte: CEDIS Vallejo")

MAXIMOS_POR_TALLA = {"XS": 3, "S": 6, "M": 6, "L": 6, "XL": 3, "XXL": 3, "XXS": 3, "3XL": 2, "4XL": 2}

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
                for v in p.get("variants", []):
                    sku = str(v.get("sku") or "").strip()
                    if sku:
                        all_variants.append({
                            "sku": sku,
                            "title_shopify": p.get("title"),
                            "image_src": image,
                            "available_compra": bool(v.get("available", False)),
                        })
            if len(products) < 250:
                break
            page += 1
        except Exception as e:
            st.warning(f"Error catálogo Shopify: {e}")
            break
    return pd.DataFrame(all_variants)

def load_master():
    """Carga la lista maestra (CLASIFICADORES)"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "lista_maestra.xlsx")
    if not os.path.exists(path):
        return None
    df = pd.read_excel(path, sheet_name="CLASIFICADORES")
    df.columns = df.columns.str.strip()
    df["SKU"] = df["SKU"].astype(str).str.strip()
    df = df[df["SKU"].notna() & (df["SKU"] != "") & (df["SKU"] != "nan")].copy()
    return df

def load_existencias():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "existencias.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, low_memory=False)
    df["CLAVE_ARTICULO"] = df["CLAVE_ARTICULO"].astype(str).str.strip()
    return df

def load_and_build():
    df_master = load_master()
    if df_master is None:
        return None, "No se encontró lista_maestra.xlsx (hoja CLASIFICADORES)"

    # Base: todos los productos de la lista maestra
    df = df_master[["SKU", "DESCRIPCIÓN", "MODELO", "COLOR", "TALLA", "COLECCIÓN", "GENERO", "TIPO"]].copy()
    df = df.rename(columns={
        "SKU": "sku",
        "DESCRIPCIÓN": "nombre",
        "MODELO": "modelo",
        "COLOR": "color",
        "TALLA": "talla",
        "COLECCIÓN": "coleccion",
        "GENERO": "genero",
        "TIPO": "tipo",
    })
    df["sku"] = df["sku"].astype(str).str.strip()
    df["color"] = df["color"].fillna("").astype(str).str.strip().str.upper()
    df["talla"] = df["talla"].fillna("").astype(str).str.strip().str.upper()
    df["coleccion"] = df["coleccion"].fillna("SIN COLECCIÓN").astype(str).str.strip()
    df["nombre_grupo"] = df["nombre"].astype(str).str.replace(r'\s*\(COLOR:.*$', '', regex=True).str.strip()

    # Stock desde existencias
    df_ex = load_existencias()
    if df_ex is not None:
        df_ex = df_ex[df_ex["SUCURSAL"].isin(["SHOPIFY", "CEDIS VALLEJO"])].copy()
        stock = df_ex.groupby(["CLAVE_ARTICULO", "SUCURSAL"])["Suma de EXISTENCIA"].sum().reset_index()
        stock = stock.pivot(index="CLAVE_ARTICULO", columns="SUCURSAL", values="Suma de EXISTENCIA").fillna(0).reset_index()
        stock.columns.name = None
        stock = stock.rename(columns={"CLAVE_ARTICULO": "sku"})
        df = df.merge(stock, on="sku", how="left")
    else:
        df["SHOPIFY"] = 0
        df["CEDIS VALLEJO"] = 0

    for col in ["SHOPIFY", "CEDIS VALLEJO"]:
        if col not in df.columns:
            df[col] = 0
    df["stock_shopify"] = df["SHOPIFY"].fillna(0).astype(int)
    df["stock_cedis"] = df["CEDIS VALLEJO"].fillna(0).astype(int)

    # Catálogo Shopify (imágenes + publicado)
    with st.spinner("Cargando catálogo de gallantdale.com..."):
        df_shop = fetch_shopify_catalog()
    df = df.merge(df_shop, on="sku", how="left")

    df["visible_web"] = df["title_shopify"].notna()
    df["se_puede_comprar"] = df["available_compra"].fillna(False)

    df["talla_norm"] = df["talla"].fillna("").astype(str).str.strip().str.upper()
    df["maximo"] = df["talla_norm"].map(MAXIMOS_POR_TALLA).fillna(0).astype(int)
    df["resurtido_sugerido"] = (df["maximo"] - df["stock_shopify"]).clip(lower=0)
    df["se_puede_surtir"] = df["stock_cedis"] >= df["resurtido_sugerido"]

    return df, None

df, error = load_and_build()
if error:
    st.error(error)
    st.info("""
    Necesitas dos archivos en la raíz del repositorio:
    - `lista_maestra.xlsx` (tu archivo de clasificadores)
    - `existencias.csv` (el de existencias diarias)
    """)
    st.stop()

# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.header("Filtros")

vista = st.sidebar.radio("Vista", [
    "Agrupada por producto",
    "Stock Shopify pero NO publicado en web",
    "ALERTA: No publicado en web pero sí en CEDIS",
    "Resurtido sugerido (con CEDIS)",
    "Detalle por SKU",
])

colecciones = ["Todas"] + sorted(df["coleccion"].dropna().unique().tolist())
coleccion_sel = st.sidebar.selectbox("Colección", colecciones)

modelos = ["Todos"] + sorted(df["modelo"].dropna().unique().tolist())
modelo_sel = st.sidebar.selectbox("Modelo", modelos)

buscar = st.sidebar.text_input("Buscar")

df_filt = df.copy()
if coleccion_sel != "Todas":
    df_filt = df_filt[df_filt["coleccion"] == coleccion_sel]
if modelo_sel != "Todos":
    df_filt = df_filt[df_filt["modelo"] == modelo_sel]
if buscar:
    mask = df_filt["sku"].str.contains(buscar, case=False, na=False) | \
           df_filt["nombre_grupo"].fillna("").str.contains(buscar, case=False, na=False)
    df_filt = df_filt[mask]

# ============================================================
# MÉTRICAS
# ============================================================
c1, c2, c3, c4 = st.columns(4)
c1.metric("SKUs", len(df_filt))
c2.metric("Con stock CEDIS", int((df_filt["stock_cedis"] > 0).sum()))
c3.metric("NO publicado + CEDIS sí", int((~df_filt["visible_web"] & (df_filt["stock_cedis"] > 0)).sum()))
c4.metric("Resurtido sugerido", int(df_filt["resurtido_sugerido"].sum()))

st.divider()

# ============================================================
# VISTA AGRUPADA (sin paginación, todos corridos)
# ============================================================
if vista == "Agrupada por producto":
    st.subheader("Productos agrupados (todas las variantes)")
    st.caption("Se muestran todas las tallas y colores aunque no tengan stock.")

    grupos = df_filt.groupby("nombre_grupo")
    nombres = sorted([n for n in grupos.groups.keys() if n])

    for nombre in nombres:
        grupo = grupos.get_group(nombre)
        img = grupo["image_src"].dropna().iloc[0] if grupo["image_src"].notna().any() else None
        total_cedis = int(grupo["stock_cedis"].sum())
        total_shop = int(grupo["stock_shopify"].sum())
        no_publicado = int((~grupo["visible_web"]).sum())
        no_publicado_con_stock = int(((grupo["stock_shopify"] > 0) & ~grupo["visible_web"]).sum())

        with st.container():
            c1, c2 = st.columns([1, 3])
            with c1:
                if img:
                    st.image(img, use_container_width=True)
                else:
                    st.info("Sin imagen")
            with c2:
                st.markdown(f"### {nombre}")
                st.caption(f"Colección: {grupo['coleccion'].iloc[0]} | Modelo: {grupo['modelo'].iloc[0]}")
                if no_publicado_con_stock > 0:
                    st.error(f"⚠️ {no_publicado_con_stock} variantes con stock Shopify pero NO publicadas")
                st.write(f"CEDIS: **{total_cedis}** | Shopify: **{total_shop}** | Variantes: **{len(grupo)}**")

                vars_df = grupo[["sku", "color", "talla", "stock_shopify", "stock_cedis",
                                 "maximo", "resurtido_sugerido", "visible_web"]].copy()
                vars_df = vars_df.sort_values(["color", "talla"])
                vars_df["Estado"] = vars_df.apply(
                    lambda r: "🔴 No publicado + stock" if (r["stock_shopify"] > 0 and not r["visible_web"])
                    else ("🟠 No publicado" if not r["visible_web"]
                          else ("✅ Publicado" if r["visible_web"] else "⚪")),
                    axis=1
                )
                st.dataframe(vars_df, hide_index=True, use_container_width=True)
            st.divider()

# ============================================================
# OTRAS VISTAS
# ============================================================
elif vista == "Stock Shopify pero NO publicado en web":
    st.subheader("⚠️ Stock en Shopify pero NO publicado en la web")
    problema = df_filt[(df_filt["stock_shopify"] > 0) & (~df_filt["visible_web"])].copy()
    if problema.empty:
        st.success("No hay productos en esta situación.")
    else:
        st.metric("SKUs", len(problema))
        st.dataframe(
            problema[["sku", "nombre_grupo", "coleccion", "color", "talla", "stock_shopify", "stock_cedis"]],
            use_container_width=True, hide_index=True
        )

elif vista == "ALERTA: No publicado en web pero sí en CEDIS":
    st.subheader("⚠️ NO publicados en web pero CON stock en CEDIS")
    alerta = df_filt[(~df_filt["visible_web"]) & (df_filt["stock_cedis"] > 0)].copy()
    if alerta.empty:
        st.success("Ninguno en esta situación.")
    else:
        st.metric("SKUs a revisar", len(alerta))
        st.dataframe(
            alerta[["sku", "nombre_grupo", "coleccion", "color", "talla", "stock_shopify", "stock_cedis", "maximo"]],
            use_container_width=True, hide_index=True
        )

elif vista == "Resurtido sugerido (con CEDIS)":
    st.subheader("Resurtido sugerido según máximos por talla")
    falt = df_filt[df_filt["resurtido_sugerido"] > 0].copy()
    if falt.empty:
        st.success("Todo está al máximo.")
    else:
        st.metric("Piezas totales a resurtir", int(falt["resurtido_sugerido"].sum()))
        st.dataframe(
            falt[["sku", "nombre_grupo", "coleccion", "color", "talla", "stock_shopify", "maximo",
                  "resurtido_sugerido", "stock_cedis", "se_puede_surtir"]],
            use_container_width=True, hide_index=True
        )

else:
    st.subheader("Detalle por SKU")
    st.dataframe(
        df_filt[["sku", "nombre_grupo", "coleccion", "color", "talla", "stock_shopify", "stock_cedis",
                 "maximo", "resurtido_sugerido", "visible_web"]],
        use_container_width=True, hide_index=True
    )

st.divider()
st.caption("Base: lista maestra (todas las variantes). Stock: existencias.csv. Publicado: aparece en gallantdale.com")
