import streamlit as st
import pandas as pd
import requests
import os
from datetime import datetime

st.set_page_config(
    page_title="Panel de Inventario - Piloto Shopify",
    page_icon="📦",
    layout="wide"
)

st.title("📦 Panel de Inventario - Piloto Shopify")
st.caption("Canal: Shopify (gallantdale.com) | Almacén que surte: CEDIS Vallejo")

# ============================================================
# MÁXIMOS POR TALLA (definidos por el usuario)
# ============================================================
MAXIMOS_POR_TALLA = {
    "XS": 3,
    "S": 6,
    "M": 6,
    "L": 6,
    "XL": 3,
    "XXL": 3,
}

@st.cache_data(ttl=3600)  # cache 1 hora
def fetch_shopify_catalog():
    """Extrae productos, imágenes y disponibilidad desde gallantdale.com/products.json"""
    base = "https://gallantdale.com/products.json"
    all_variants = []
    page = 1
    while True:
        try:
            r = requests.get(f"{base}?limit=250&page={page}", timeout=30)
            if r.status_code != 200:
                break
            data = r.json()
            products = data.get("products", [])
            if not products:
                break
            for p in products:
                image = p["images"][0]["src"] if p.get("images") else None
                for v in p.get("variants", []):
                    all_variants.append({
                        "sku": str(v.get("sku") or "").strip(),
                        "title": p.get("title"),
                        "image_src": image,
                        "product_url": f"https://gallantdale.com/products/{p.get('handle')}",
                        "available": bool(v.get("available", False)),
                        "price": float(v.get("price") or 0),
                    })
            if len(products) < 250:
                break
            page += 1
            if page > 30:  # seguridad
                break
        except Exception as e:
            st.warning(f"Error obteniendo catálogo Shopify: {e}")
            break
    return pd.DataFrame(all_variants)

@st.cache_data
def load_existencias():
    """Carga el CSV de existencias que debe estar en la misma carpeta"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "existencias.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, low_memory=False)
    df["CLAVE_ARTICULO"] = df["CLAVE_ARTICULO"].astype(str).str.strip()
    return df

def build_dataset():
    df_ex = load_existencias()
    if df_ex is None:
        return None, "No se encontró existencias.csv"

    # Stock por sucursal
    sucursales = ["SHOPIFY", "CEDIS VALLEJO"]
    df_stock = df_ex[df_ex["SUCURSAL"].isin(sucursales)].copy()
    df_stock = df_stock.groupby(["CLAVE_ARTICULO", "SUCURSAL"])["Suma de EXISTENCIA"].sum().reset_index()
    df_stock = df_stock.pivot(index="CLAVE_ARTICULO", columns="SUCURSAL", values="Suma de EXISTENCIA").fillna(0).reset_index()
    df_stock.columns.name = None
    df_stock = df_stock.rename(columns={"CLAVE_ARTICULO": "sku"})
    for s in sucursales:
        if s not in df_stock.columns:
            df_stock[s] = 0

    # Catálogo Shopify (imágenes + disponibilidad)
    with st.spinner("Obteniendo catálogo e imágenes de gallantdale.com..."):
        df_shop = fetch_shopify_catalog()

    # Unir
    df = df_stock.merge(df_shop, on="sku", how="left")

    # Máximos por talla
    df["talla_norm"] = df["talla"].astype(str).str.strip().str.upper() if "talla" in df.columns else ""
    # Si no viene talla del CSV, intentar de option o del SKU (simplificado)
    df["maximo"] = df.apply(
        lambda r: MAXIMOS_POR_TALLA.get(str(r.get("talla", "")).strip().upper(), 0),
        axis=1
    )

    # Campos finales
    df["stock_shopify"] = df["SHOPIFY"].fillna(0).astype(int)
    df["stock_cedis"] = df["CEDIS VALLEJO"].fillna(0).astype(int)
    df["visible_web"] = df["available"].fillna(False)
    df["resurtido_sugerido"] = (df["maximo"] - df["stock_shopify"]).clip(lower=0)

    return df, None

# ============================================================
# CARGA
# ============================================================
df, error = build_dataset()

if error:
    st.error(error)
    st.info("""
    **Cómo actualizar las existencias diarias:**
    1. Descarga el CSV de existencias (el mismo formato que el que me compartiste).
    2. Renómbralo exactamente a `existencias.csv`.
    3. Súbelo a tu repositorio de GitHub (misma carpeta que `app.py`).
    4. Haz commit y push.
    5. Render detecta el cambio y redespliega automáticamente (o haz Manual Deploy).
    
    Así no tienes que tocar el código, solo reemplazas el archivo de datos.
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
        "Detalle por SKU",
        "Resumen faltantes Shopify",
    ]
)

modelos = ["Todos"] + sorted(df["title"].dropna().unique().tolist())
modelo_sel = st.sidebar.selectbox("Modelo / Producto", modelos)

buscar = st.sidebar.text_input("Buscar SKU o nombre")

# Filtros
df_filt = df.copy()
if modelo_sel != "Todos":
    df_filt = df_filt[df_filt["title"] == modelo_sel]
if buscar:
    mask = df_filt["sku"].str.contains(buscar, case=False, na=False) | \
           df_filt["title"].fillna("").str.contains(buscar, case=False, na=False)
    df_filt = df_filt[mask]

# ============================================================
# MÉTRICAS
# ============================================================
col1, col2, col3, col4 = st.columns(4)
col1.metric("SKUs", len(df_filt))
col2.metric("Con stock CEDIS", int((df_filt["stock_cedis"] > 0).sum()))
col3.metric("No visible web + sí CEDIS", int((~df_filt["visible_web"] & (df_filt["stock_cedis"] > 0)).sum()))
col4.metric("Resurtido sugerido", int(df_filt["resurtido_sugerido"].sum()))

st.divider()

# ============================================================
# VISTA PRINCIPAL: ALERTA NO VISIBLE PERO SÍ CEDIS
# ============================================================
if vista == "ALERTA: No visible en web pero sí en CEDIS":
    st.subheader("⚠️ Productos NO visibles en gallantdale.com pero CON stock en CEDIS Vallejo")
    st.caption("Estos son los que se están dejando de vender. Hay que hacer el traspaso a Shopify para que vuelvan a estar disponibles.")

    alerta = df_filt[(~df_filt["visible_web"]) & (df_filt["stock_cedis"] > 0)].copy()
    alerta = alerta.sort_values(["title", "sku"])

    if alerta.empty:
        st.success("No hay productos en esta situación con los filtros actuales.")
    else:
        st.metric("SKUs que necesitan traspaso", len(alerta))
        st.dataframe(
            alerta[["sku", "title", "stock_shopify", "stock_cedis", "maximo", "visible_web"]],
            use_container_width=True,
            hide_index=True
        )

        # Agrupado
        st.subheader("Vista agrupada")
        for nombre, grupo in alerta.groupby("title"):
            with st.expander(f"{nombre} — {len(grupo)} variantes", expanded=False):
                img = grupo["image_src"].dropna().iloc[0] if grupo["image_src"].notna().any() else None
                c1, c2 = st.columns([1, 3])
                with c1:
                    if img:
                        st.image(img, use_container_width=True)
                with c2:
                    st.dataframe(
                        grupo[["sku", "stock_shopify", "stock_cedis", "maximo"]],
                        hide_index=True,
                        use_container_width=True
                    )

# ============================================================
# VISTA AGRUPADA (la que te gustó)
# ============================================================
elif vista == "Agrupada por producto":
    st.subheader("Productos agrupados (imagen + variantes)")

    grupos = df_filt.groupby("title")
    items_per_page = 6
    nombres = sorted([n for n in grupos.groups.keys() if pd.notna(n)])
    total_pages = max(1, (len(nombres) - 1) // items_per_page + 1)
    page = st.number_input("Página", min_value=1, max_value=total_pages, value=1)
    start = (page - 1) * items_per_page
    end = start + items_per_page

    for nombre in nombres[start:end]:
        grupo = grupos.get_group(nombre)
        img = grupo["image_src"].dropna().iloc[0] if grupo["image_src"].notna().any() else None
        total_cedis = int(grupo["stock_cedis"].sum())
        total_shop = int(grupo["stock_shopify"].sum())
        no_visibles = int((~grupo["visible_web"] & (grupo["stock_cedis"] > 0)).sum())

        with st.container():
            c1, c2 = st.columns([1, 3])
            with c1:
                if img:
                    st.image(img, use_container_width=True)
                else:
                    st.info("Sin imagen")

            with c2:
                st.markdown(f"### {nombre}")
                if no_visibles > 0:
                    st.error(f"⚠️ {no_visibles} variantes NO visibles en web pero con stock en CEDIS")
                st.write(f"Stock total CEDIS: **{total_cedis}** | Shopify: **{total_shop}**")

                variantes = grupo[["sku", "stock_shopify", "stock_cedis", "maximo", "visible_web", "resurtido_sugerido"]].copy()
                variantes["Estado"] = variantes.apply(
                    lambda r: "🔴 No visible + CEDIS sí" if (not r["visible_web"] and r["stock_cedis"] > 0)
                    else ("✅ Visible" if r["visible_web"] else "⚪ No visible"),
                    axis=1
                )
                st.dataframe(variantes, hide_index=True, use_container_width=True)

            st.divider()

# ============================================================
# OTRAS VISTAS
# ============================================================
elif vista == "Resumen faltantes Shopify":
    st.subheader("Resumen de faltantes en Shopify (según máximos por talla)")
    faltantes = df_filt[df_filt["resurtido_sugerido"] > 0].copy()
    if faltantes.empty:
        st.success("Shopify está al máximo en todo lo filtrado.")
    else:
        st.metric("Piezas a resurtir", int(faltantes["resurtido_sugerido"].sum()))
        st.dataframe(
            faltantes[["sku", "title", "stock_shopify", "maximo", "resurtido_sugerido", "stock_cedis"]],
            use_container_width=True,
            hide_index=True
        )

else:
    st.subheader("Detalle por SKU")
    st.dataframe(
        df_filt[["sku", "title", "stock_shopify", "stock_cedis", "maximo", "visible_web", "resurtido_sugerido"]],
        use_container_width=True,
        hide_index=True
    )

st.divider()
st.caption(f"Máximos por talla: XS=3, S=6, M=6, L=6, XL=3, XXL=3. Datos de existencias: archivo local. Catálogo e imágenes: gallantdale.com en vivo.")
