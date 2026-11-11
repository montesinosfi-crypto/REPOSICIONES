import streamlit as st
import pandas as pd
import requests
import os
import re

st.set_page_config(
    page_title="Panel de Inventario - Piloto Shopify",
    page_icon="📦",
    layout="wide"
)

st.title("📦 Panel de Inventario - Piloto Shopify")
st.caption("Canal: Shopify (gallantdale.com) | Almacén que surte: CEDIS Vallejo")

# Máximos por talla definidos por el usuario
MAXIMOS_POR_TALLA = {
    "XS": 3, "S": 6, "M": 6, "L": 6, "XL": 3, "XXL": 3,
    "XXS": 3, "3XL": 2, "4XL": 2,
}

@st.cache_data(ttl=3600)
def fetch_shopify_catalog():
    """Extrae catálogo, imágenes y disponibilidad desde gallantdale.com"""
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
                    if not sku:
                        continue
                    all_variants.append({
                        "sku": sku,
                        "title_shopify": p.get("title"),
                        "image_src": image,
                        "product_url": f"https://gallantdale.com/products/{p.get('handle')}",
                        "available": bool(v.get("available", False)),
                        "price": float(v.get("price") or 0),
                    })
            if len(products) < 250:
                break
            page += 1
        except Exception as e:
            st.warning(f"No se pudo obtener catálogo Shopify: {e}")
            break
    return pd.DataFrame(all_variants)

def extract_talla_from_name(nombre):
    """Extrae talla del nombre si viene como (COLOR: XX/TALLA: YY)"""
    if pd.isna(nombre):
        return None
    m = re.search(r'TALLA:\s*([A-Z0-9]+)', str(nombre), re.IGNORECASE)
    return m.group(1).upper() if m else None

def load_and_build():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "existencias.csv")
    if not os.path.exists(path):
        return None, "No se encontró existencias.csv en la carpeta del proyecto."

    df_ex = pd.read_csv(path, low_memory=False)
    df_ex["CLAVE_ARTICULO"] = df_ex["CLAVE_ARTICULO"].astype(str).str.strip()

    # Quedarnos solo con Shopify y CEDIS VALLEJO
    df_ex = df_ex[df_ex["SUCURSAL"].isin(["SHOPIFY", "CEDIS VALLEJO"])].copy()

    # Extraer talla del nombre si la columna está vacía
    df_ex["talla_extraida"] = df_ex.apply(
        lambda r: r["TALLA"] if pd.notna(r["TALLA"]) and str(r["TALLA"]).strip() 
        else extract_talla_from_name(r["NOMBRE_ARTICULO"]),
        axis=1
    )
    df_ex["color_limpio"] = df_ex["COLOR"].fillna("").astype(str).str.strip().str.upper()

    # Agrupar stock por SKU + sucursal
    stock = df_ex.groupby(["CLAVE_ARTICULO", "SUCURSAL"])["Suma de EXISTENCIA"].sum().reset_index()
    stock = stock.pivot(index="CLAVE_ARTICULO", columns="SUCURSAL", values="Suma de EXISTENCIA").fillna(0).reset_index()
    stock.columns.name = None
    stock = stock.rename(columns={"CLAVE_ARTICULO": "sku"})

    # Información del producto (una fila por SKU)
    info = df_ex.groupby("CLAVE_ARTICULO").agg({
        "NOMBRE_ARTICULO": "first",
        "talla_extraida": "first",
        "color_limpio": "first",
        "COLECC": "first",
    }).reset_index().rename(columns={
        "CLAVE_ARTICULO": "sku",
        "NOMBRE_ARTICULO": "nombre",
        "talla_extraida": "talla",
        "color_limpio": "color",
        "COLECC": "coleccion",
    })

    df = info.merge(stock, on="sku", how="left")
    for col in ["SHOPIFY", "CEDIS VALLEJO"]:
        if col not in df.columns:
            df[col] = 0
    df["stock_shopify"] = df["SHOPIFY"].fillna(0).astype(int)
    df["stock_cedis"] = df["CEDIS VALLEJO"].fillna(0).astype(int)

    # Catálogo Shopify (imágenes + visibilidad)
    with st.spinner("Cargando imágenes y disponibilidad desde gallantdale.com..."):
        df_shop = fetch_shopify_catalog()

    df = df.merge(df_shop, on="sku", how="left")

    # Máximo según talla
    df["talla_norm"] = df["talla"].fillna("").astype(str).str.strip().str.upper()
    df["maximo"] = df["talla_norm"].map(MAXIMOS_POR_TALLA).fillna(0).astype(int)
    df["resurtido_sugerido"] = (df["maximo"] - df["stock_shopify"]).clip(lower=0)
    df["visible_web"] = df["available"].fillna(False)

    # Nombre limpio para agrupar (quitar el paréntesis de color/talla)
    df["nombre_grupo"] = df["nombre"].astype(str).str.replace(r'\s*\(COLOR:.*$', '', regex=True).str.strip()

    return df, None

# ============================================================
# CARGA
# ============================================================
df, error = load_and_build()

if error:
    st.error(error)
    st.info("""
    **Cómo actualizar existencias:**
    1. Descarga tu CSV de existencias.
    2. Renómbralo a `existencias.csv`.
    3. Súbelo a tu repositorio de GitHub (misma carpeta que app.py).
    4. Commit + push. Render se actualiza solo o haz Manual Deploy.
    """)
    st.stop()

# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.header("Filtros")

vista = st.sidebar.radio(
    "Vista",
    [
        "Agrupada por producto",
        "ALERTA: No visible en web pero sí en CEDIS",
        "Resumen faltantes Shopify",
        "Detalle por SKU",
    ]
)

modelos = ["Todos"] + sorted(df["nombre_grupo"].dropna().unique().tolist())
modelo_sel = st.sidebar.selectbox("Modelo", modelos)

buscar = st.sidebar.text_input("Buscar")

df_filt = df.copy()
if modelo_sel != "Todos":
    df_filt = df_filt[df_filt["nombre_grupo"] == modelo_sel]
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
c3.metric("No visible + CEDIS sí", int((~df_filt["visible_web"] & (df_filt["stock_cedis"] > 0)).sum()))
c4.metric("Resurtido sugerido", int(df_filt["resurtido_sugerido"].sum()))

st.divider()

# ============================================================
# VISTA AGRUPADA (la que te gustó)
# ============================================================
if vista == "Agrupada por producto":
    st.subheader("Productos agrupados")

    grupos = df_filt.groupby("nombre_grupo")
    nombres = sorted([n for n in grupos.groups.keys() if n])
    items_per_page = 5
    total_pages = max(1, (len(nombres) - 1) // items_per_page + 1)
    page = st.number_input("Página", min_value=1, max_value=total_pages, value=1)
    start = (page - 1) * items_per_page
    end = start + items_per_page

    for nombre in nombres[start:end]:
        grupo = grupos.get_group(nombre)
        img = grupo["image_src"].dropna().iloc[0] if grupo["image_src"].notna().any() else None
        total_cedis = int(grupo["stock_cedis"].sum())
        total_shop = int(grupo["stock_shopify"].sum())
        no_vis = int((~grupo["visible_web"] & (grupo["stock_cedis"] > 0)).sum())
        resurtido = int(grupo["resurtido_sugerido"].sum())

        with st.container():
            c1, c2 = st.columns([1, 3])
            with c1:
                if img:
                    st.image(img, use_container_width=True)
                else:
                    st.info("Sin imagen")

            with c2:
                st.markdown(f"### {nombre}")
                if no_vis > 0:
                    st.error(f"⚠️ {no_vis} variantes NO visibles en web pero con stock en CEDIS")
                if resurtido > 0:
                    st.warning(f"Resurtido sugerido: {resurtido} piezas")
                st.write(f"CEDIS: **{total_cedis}** | Shopify: **{total_shop}**")

                vars_df = grupo[["sku", "color", "talla", "stock_shopify", "stock_cedis", "maximo", "resurtido_sugerido", "visible_web"]].copy()
                vars_df["Estado"] = vars_df.apply(
                    lambda r: "🔴 No visible + CEDIS" if (not r["visible_web"] and r["stock_cedis"] > 0)
                    else ("✅ Visible" if r["visible_web"] else "⚪ No visible"),
                    axis=1
                )
                st.dataframe(vars_df, hide_index=True, use_container_width=True)

            st.divider()

# ============================================================
# ALERTA PRINCIPAL
# ============================================================
elif vista == "ALERTA: No visible en web pero sí en CEDIS":
    st.subheader("⚠️ Productos NO visibles en gallantdale.com pero CON stock en CEDIS")
    st.caption("Estos hay que traspasar a Shopify para que vuelvan a venderse.")

    alerta = df_filt[(~df_filt["visible_web"]) & (df_filt["stock_cedis"] > 0)].copy()
    if alerta.empty:
        st.success("No hay productos en esta situación.")
    else:
        st.metric("SKUs a traspasar", len(alerta))
        st.dataframe(
            alerta[["sku", "nombre_grupo", "color", "talla", "stock_shopify", "stock_cedis", "maximo"]],
            use_container_width=True, hide_index=True
        )

# ============================================================
# RESUMEN FALTANTES
# ============================================================
elif vista == "Resumen faltantes Shopify":
    st.subheader("Faltantes en Shopify según máximos por talla")
    falt = df_filt[df_filt["resurtido_sugerido"] > 0].copy()
    if falt.empty:
        st.success("Todo está al máximo.")
    else:
        st.metric("Piezas a resurtir", int(falt["resurtido_sugerido"].sum()))
        st.dataframe(
            falt[["sku", "nombre_grupo", "color", "talla", "stock_shopify", "maximo", "resurtido_sugerido", "stock_cedis"]],
            use_container_width=True, hide_index=True
        )

# ============================================================
# DETALLE
# ============================================================
else:
    st.subheader("Detalle por SKU")
    st.dataframe(
        df_filt[["sku", "nombre_grupo", "color", "talla", "stock_shopify", "stock_cedis", "maximo", "resurtido_sugerido", "visible_web"]],
        use_container_width=True, hide_index=True
    )

st.divider()
st.caption("Máximos: XS=3, S=6, M=6, L=6, XL=3, XXL=3. Talla y color se toman del archivo de existencias.")
