import streamlit as st
import pandas as pd
import os

st.set_page_config(
    page_title="Panel de Inventario - Piloto Shopify",
    page_icon="📦",
    layout="wide"
)

st.title("📦 Panel de Inventario - Piloto Shopify")
st.caption("Canal: Shopify | Almacén que surte: CEDIS Vallejo")

@st.cache_data
def load_data():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "productos_piloto.csv")
    if not os.path.exists(path):
        st.error(f"No se encontró el archivo: {path}")
        return pd.DataFrame()
    df = pd.read_csv(path)
    for col in ['tiene_stock', 'stock_cedis', 'stock_shopify', 'maximos']:
        df[col] = df[col].fillna(0).astype(int)
    return df

df = load_data()
if df.empty:
    st.stop()

# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.header("Filtros")

vista = st.sidebar.radio(
    "Vista",
    ["Agrupada por producto", "Detalle por SKU", "Alerta: Shopify sí / CEDIS no"]
)

colecciones = ["Todas"] + sorted(df['coleccion'].dropna().unique().tolist())
colores = ["Todos"] + sorted(df['color'].dropna().unique().tolist())
tallas = ["Todas"] + sorted(df['talla'].dropna().unique().tolist())

coleccion_sel = st.sidebar.selectbox("Colección", colecciones)
color_sel = st.sidebar.selectbox("Color", colores)
talla_sel = st.sidebar.selectbox("Talla", tallas)
buscar = st.sidebar.text_input("Buscar nombre o SKU")

# Filtros base
df_filt = df.copy()
if coleccion_sel != "Todas":
    df_filt = df_filt[df_filt['coleccion'] == coleccion_sel]
if color_sel != "Todos":
    df_filt = df_filt[df_filt['color'] == color_sel]
if talla_sel != "Todas":
    df_filt = df_filt[df_filt['talla'] == talla_sel]
if buscar:
    mask = df_filt['sku'].str.contains(buscar, case=False, na=False) | \
           df_filt['nombre'].str.contains(buscar, case=False, na=False)
    df_filt = df_filt[mask]

# ============================================================
# MÉTRICAS GLOBALES
# ============================================================
col1, col2, col3, col4 = st.columns(4)
col1.metric("SKUs filtrados", len(df_filt))
col2.metric("Con stock CEDIS", int((df_filt['stock_cedis'] > 0).sum()))
col3.metric("Shopify > 0 y CEDIS = 0", int(((df_filt['stock_shopify'] > 0) & (df_filt['stock_cedis'] == 0)).sum()))
col4.metric("Stock total CEDIS", int(df_filt['stock_cedis'].sum()))

st.divider()

# ============================================================
# VISTA: ALERTA (Shopify sí / CEDIS no)
# ============================================================
if vista == "Alerta: Shopify sí / CEDIS no":
    st.subheader("⚠️ Productos que Shopify tiene y CEDIS NO")
    st.caption("Estos son los que provocan ruptura de stock y dejas de vender.")

    alerta = df_filt[(df_filt['stock_shopify'] > 0) & (df_filt['stock_cedis'] == 0)].copy()
    alerta = alerta.sort_values(['nombre', 'color', 'talla'])

    if alerta.empty:
        st.success("No hay productos en esta situación con los filtros actuales.")
    else:
        st.metric("SKUs en riesgo", len(alerta))
        st.dataframe(
            alerta[['sku', 'nombre', 'coleccion', 'color', 'talla', 'stock_shopify', 'stock_cedis', 'maximos']],
            use_container_width=True,
            hide_index=True
        )

        st.subheader("Vista agrupada")
        for nombre, grupo in alerta.groupby('nombre'):
            with st.expander(f"{nombre}  —  {len(grupo)} tallas/colores sin stock en CEDIS", expanded=False):
                img = grupo['image_src'].dropna().iloc[0] if grupo['image_src'].notna().any() else None
                c1, c2 = st.columns([1, 3])
                with c1:
                    if img:
                        st.image(img, use_container_width=True)
                with c2:
                    st.dataframe(
                        grupo[['sku', 'color', 'talla', 'stock_shopify', 'maximos']],
                        hide_index=True,
                        use_container_width=True
                    )

# ============================================================
# VISTA: AGRUPADA POR PRODUCTO
# ============================================================
elif vista == "Agrupada por producto":
    st.subheader("Productos agrupados (mismo modelo, diferentes colores/tallas)")

    # Agrupar
    grupos = df_filt.groupby('nombre')

    items_per_page = 8
    nombres = sorted(grupos.groups.keys())
    total_pages = max(1, (len(nombres) - 1) // items_per_page + 1)
    page = st.number_input("Página", min_value=1, max_value=total_pages, value=1)
    start = (page - 1) * items_per_page
    end = start + items_per_page

    for nombre in nombres[start:end]:
        grupo = grupos.get_group(nombre)
        img = grupo['image_src'].dropna().iloc[0] if grupo['image_src'].notna().any() else None
        coleccion = grupo['coleccion'].iloc[0]
        total_cedis = int(grupo['stock_cedis'].sum())
        total_shop = int(grupo['stock_shopify'].sum())
        skus_riesgo = int(((grupo['stock_shopify'] > 0) & (grupo['stock_cedis'] == 0)).sum())

        with st.container():
            c1, c2 = st.columns([1, 3])
            with c1:
                if img:
                    st.image(img, use_container_width=True)
                else:
                    st.info("Sin imagen")

            with c2:
                st.markdown(f"### {nombre}")
                st.caption(f"Colección: {coleccion}")

                if skus_riesgo > 0:
                    st.error(f"⚠️ {skus_riesgo} variantes con stock en Shopify y sin stock en CEDIS")
                elif total_cedis > 0:
                    st.success(f"CEDIS: {total_cedis}  |  Shopify: {total_shop}")
                else:
                    st.warning("Sin stock en CEDIS")

                # Tabla de variantes
                variantes = grupo[['sku', 'color', 'talla', 'stock_shopify', 'stock_cedis', 'maximos']].copy()
                variantes['Estado'] = variantes.apply(
                    lambda r: '🔴 Shopify sí / CEDIS no' if r['stock_shopify'] > 0 and r['stock_cedis'] == 0
                    else ('✅' if r['stock_cedis'] > 0 else '⚪ Sin stock'),
                    axis=1
                )
                st.dataframe(variantes, hide_index=True, use_container_width=True)

            st.divider()

# ============================================================
# VISTA: DETALLE POR SKU (original)
# ============================================================
else:
    st.subheader("Detalle por SKU")
    df_show = df_filt[['sku', 'nombre', 'coleccion', 'color', 'talla',
                       'stock_shopify', 'stock_cedis', 'maximos']].copy()
    df_show['Estado'] = df_show.apply(
        lambda r: '🔴 Shopify sí / CEDIS no' if r['stock_shopify'] > 0 and r['stock_cedis'] == 0
        else ('✅ Con stock CEDIS' if r['stock_cedis'] > 0 else '⚪ Sin stock'),
        axis=1
    )
    st.dataframe(df_show, use_container_width=True, hide_index=True)

st.divider()
st.caption("Datos de piloto: Shopify (canal) + CEDIS Vallejo (almacén). Imágenes de gallantdale.com")
