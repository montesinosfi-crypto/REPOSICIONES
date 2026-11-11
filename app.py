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
                            "product_url": f"https://gallantdale.com/products/{p.get('handle')}",
                            "available": bool(v.get("available", False)),
                        })
            if len(products) < 250:
                break
            page += 1
        except Exception as e:
            st.warning(f"Error catálogo Shopify: {e}")
            break
    return pd.DataFrame(all_variants)

def extract_talla_from_name(nombre):
    if pd.isna(nombre):
        return None
    m = re.search(r'TALLA:\s*([A-Z0-9]+)', str(nombre), re.IGNORECASE)
    return m.group(1).upper() if m else None

def load_and_build():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "existencias.csv")
    if not os.path.exists(path):
        return None, "No se encontró existencias.csv"

    df_ex = pd.read_csv(path, low_memory=False)
    df_ex["CLAVE_ARTICULO"] = df_ex["CLAVE_ARTICULO"].astype(str).str.strip()
    df_ex = df_ex[df_ex["SUCURSAL"].isin(["SHOPIFY", "CEDIS VALLEJO"])].copy()

    df_ex["talla_extraida"] = df_ex.apply(
        lambda r: r["TALLA"] if pd.notna(r["TALLA"]) and str(r["TALLA"]).strip()
        else extract_talla_from_name(r["NOMBRE_ARTICULO"]), axis=1)
    df_ex["color_limpio"] = df_ex["COLOR"].fillna("").astype(str).str.strip().str.upper()

    stock = df_ex.groupby(["CLAVE_ARTICULO", "SUCURSAL"])["Suma de EXISTENCIA"].sum().reset_index()
    stock = stock.pivot(index="CLAVE_ARTICULO", columns="SUCURSAL", values="Suma de EXISTENCIA").fillna(0).reset_index()
    stock.columns.name = None
    stock = stock.rename(columns={"CLAVE_ARTICULO": "sku"})

    info = df_ex.groupby("CLAVE_ARTICULO").agg({
        "NOMBRE_ARTICULO": "first",
        "talla_extraida": "first",
        "color_limpio": "first",
        "COLECC": "first",
    }).reset_index().rename(columns={
        "CLAVE_ARTICULO": "sku", "NOMBRE_ARTICULO": "nombre",
        "talla_extraida": "talla", "color_limpio": "color", "COLECC": "coleccion"
    })

    df = info.merge(stock, on="sku", how="left")
    for col in ["SHOPIFY", "CEDIS VALLEJO"]:
        if col not in df.columns:
            df[col] = 0
    df["stock_shopify"] = df["SHOPIFY"].fillna(0).astype(int)
    df["stock_cedis"] = df["CEDIS VALLEJO"].fillna(0).astype(int)

    with st.spinner("Cargando catálogo de gallantdale.com..."):
        df_shop = fetch_shopify_catalog()
    df = df.merge(df_shop, on="sku", how="left")

    df["talla_norm"] = df["talla"].fillna("").astype(str).str.strip().str.upper()
    df["maximo"] = df["talla_norm"].map(MAXIMOS_POR_TALLA).fillna(0).astype(int)
    df["resurtido_sugerido"] = (df["maximo"] - df["stock_shopify"]).clip(lower=0)
    df["visible_web"] = df["available"].fillna(False)
    df["nombre_grupo"] = df["nombre"].astype(str).str.replace(r'\s*\(COLOR:.*$', '', regex=True).str.strip()
    df["coleccion"] = df["coleccion"].fillna("SIN COLECCIÓN").astype(str).str.strip()

    df["se_puede_surtir"] = df["stock_cedis"] >= df["resurtido_sugerido"]
    df["faltante_despues_cedis"] = (df["resurtido_sugerido"] - df["stock_cedis"]).clip(lower=0)

    return df, None

df, error = load_and_build()
if error:
    st.error(error)
    st.info("Sube el archivo existencias.csv a la raíz del repositorio y redeploy.")
    st.stop()

# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.header("Filtros")

vista = st.sidebar.radio("Vista", [
    "Agrupada por producto",
    "Stock Shopify pero NO visible (configuración)",
    "ALERTA: No visible en web pero sí en CEDIS",
    "Resurtido sugerido (con CEDIS)",
    "Detalle por SKU",
])

# Filtro de Colección (importante)
colecciones = ["Todas"] + sorted(df["coleccion"].dropna().unique().tolist())
coleccion_sel = st.sidebar.selectbox("Colección", colecciones)

modelos = ["Todos"] + sorted(df["nombre_grupo"].dropna().unique().tolist())
modelo_sel = st.sidebar.selectbox("Modelo", modelos)

buscar = st.sidebar.text_input("Buscar")

# Aplicar filtros
df_filt = df.copy()
if coleccion_sel != "Todas":
    df_filt = df_filt[df_filt["coleccion"] == coleccion_sel]
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
c2.metric("Stock Shopify > 0 y no visible", int(((df_filt["stock_shopify"] > 0) & ~df_filt["visible_web"]).sum()))
c3.metric("No visible + CEDIS sí", int((~df_filt["visible_web"] & (df_filt["stock_cedis"] > 0)).sum()))
c4.metric("Resurtido sugerido", int(df_filt["resurtido_sugerido"].sum()))

st.divider()

# ============================================================
# VISTA: Stock Shopify pero NO visible (tal cual pediste)
# ============================================================
if vista == "Stock Shopify pero NO visible (configuración)":
    st.subheader("⚠️ Productos con existencia en almacén Shopify pero NO visibles en la web")
    st.caption("Solo se muestran los que tienen stock_shopify > 0 y available = False en gallantdale.com. Problema de configuración.")

    problema = df_filt[
        (df_filt["stock_shopify"] > 0) & (~df_filt["visible_web"])
    ].copy()

    if problema.empty:
        st.success("No hay productos con stock en Shopify y no visibles (con los filtros actuales).")
    else:
        st.metric("SKUs con problema de configuración", len(problema))

        # Agrupado por modelo para que se vea más claro
        st.subheader("Agrupado por modelo")
        for nombre, grupo in problema.groupby("nombre_grupo"):
            with st.expander(f"{nombre} — {len(grupo)} variantes", expanded=False):
                img = grupo["image_src"].dropna().iloc[0] if grupo["image_src"].notna().any() else None
                c1, c2 = st.columns([1, 3])
                with c1:
                    if img:
                        st.image(img, use_container_width=True)
                with c2:
                    st.dataframe(
                        grupo[["sku", "coleccion", "color", "talla", "stock_shopify", "stock_cedis"]],
                        hide_index=True, use_container_width=True
                    )

        st.subheader("Listado completo")
        st.dataframe(
            problema[["sku", "nombre_grupo", "coleccion", "color", "talla", "stock_shopify", "stock_cedis"]],
            use_container_width=True, hide_index=True
        )

# ============================================================
# OTRAS VISTAS (sin cambios mayores)
# ============================================================
elif vista == "ALERTA: No visible en web pero sí en CEDIS":
    st.subheader("⚠️ NO visibles en web pero CON stock en CEDIS")
    alerta = df_filt[(~df_filt["visible_web"]) & (df_filt["stock_cedis"] > 0)].copy()
    if alerta.empty:
        st.success("Ninguno en esta situación.")
    else:
        st.metric("SKUs a traspasar", len(alerta))
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

elif vista == "Agrupada por producto":
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
        config_issue = int(((grupo["stock_shopify"] > 0) & ~grupo["visible_web"]).sum())

        with st.container():
            c1, c2 = st.columns([1, 3])
            with c1:
                if img:
                    st.image(img, use_container_width=True)
                else:
                    st.info("Sin imagen")
            with c2:
                st.markdown(f"### {nombre}")
                st.caption(f"Colección: {grupo['coleccion'].iloc[0]}")
                if config_issue > 0:
                    st.error(f"⚠️ {config_issue} variantes con stock Shopify pero NO visibles")
                st.write(f"CEDIS: **{total_cedis}** | Shopify: **{total_shop}**")

                vars_df = grupo[["sku", "color", "talla", "stock_shopify", "stock_cedis",
                                 "maximo", "resurtido_sugerido", "visible_web"]].copy()
                vars_df["Estado"] = vars_df.apply(
                    lambda r: "🔴 Configuración" if (r["stock_shopify"] > 0 and not r["visible_web"])
                    else ("🟠 Traspasar" if (not r["visible_web"] and r["stock_cedis"] > 0)
                          else ("✅" if r["visible_web"] else "⚪")),
                    axis=1
                )
                st.dataframe(vars_df, hide_index=True, use_container_width=True)
            st.divider()

else:
    st.subheader("Detalle por SKU")
    st.dataframe(
        df_filt[["sku", "nombre_grupo", "coleccion", "color", "talla", "stock_shopify", "stock_cedis",
                 "maximo", "resurtido_sugerido", "visible_web"]],
        use_container_width=True, hide_index=True
    )

st.divider()
st.caption("Máximos por talla: XS=3, S=6, M=6, L=6, XL=3, XXL=3")
