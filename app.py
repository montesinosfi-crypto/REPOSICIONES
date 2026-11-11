import streamlit as st
import pandas as pd
import os

st.set_page_config(
    page_title="Inventario Gallantdale - Piloto Shopify",
    page_icon="📦",
    layout="wide"
)

st.title("📦 Dashboard de Inventario - Piloto Shopify")
st.caption("Canal: Shopify | Almacén que surte: CEDIS Vallejo")

# Cargar datos
@st.cache_data
def load_data():
    path = os.path.join(os.path.dirname(__file__), "productos_piloto.csv")
    df = pd.read_csv(path)
    df['tiene_stock'] = df['tiene_stock'].fillna(0).astype(int)
    df['stock_cedis'] = df['stock_cedis'].fillna(0).astype(int)
    df['stock_shopify'] = df['stock_shopify'].fillna(0).astype(int)
    df['maximos'] = df['maximos'].fillna(0).astype(int)
    return df

df = load_data()

# Sidebar - Filtros
st.sidebar.header("Filtros")
colecciones = ["Todas"] + sorted(df['coleccion'].dropna().unique().tolist())
colores = ["Todos"] + sorted(df['color'].dropna().unique().tolist())
tallas = ["Todas"] + sorted(df['talla'].dropna().unique().tolist())

coleccion_sel = st.sidebar.selectbox("Colección", colecciones)
color_sel = st.sidebar.selectbox("Color", colores)
talla_sel = st.sidebar.selectbox("Talla", tallas)

solo_con_stock = st.sidebar.checkbox("Solo con stock en CEDIS", value=False)
solo_sin_stock = st.sidebar.checkbox("Solo sin stock en CEDIS", value=False)
buscar = st.sidebar.text_input("Buscar SKU o nombre")

# Aplicar filtros
df_filt = df.copy()
if coleccion_sel != "Todas":
    df_filt = df_filt[df_filt['coleccion'] == coleccion_sel]
if color_sel != "Todos":
    df_filt = df_filt[df_filt['color'] == color_sel]
if talla_sel != "Todas":
    df_filt = df_filt[df_filt['talla'] == talla_sel]
if solo_con_stock:
    df_filt = df_filt[df_filt['stock_cedis'] > 0]
if solo_sin_stock:
    df_filt = df_filt[df_filt['stock_cedis'] == 0]
if buscar:
    mask = df_filt['sku'].str.contains(buscar, case=False, na=False) | \
           df_filt['nombre'].str.contains(buscar, case=False, na=False)
    df_filt = df_filt[mask]

# Métricas
col1, col2, col3, col4 = st.columns(4)
col1.metric("Productos filtrados", len(df_filt))
col2.metric("Con stock CEDIS", int((df_filt['stock_cedis'] > 0).sum()))
col3.metric("Sin stock CEDIS", int((df_filt['stock_cedis'] == 0).sum()))
col4.metric("Stock total CEDIS", int(df_filt['stock_cedis'].sum()))

st.divider()

# Tabla principal
st.subheader("Disponibilidad por Línea / Color / Talla")

df_show = df_filt[[
    'sku', 'nombre', 'coleccion', 'color', 'talla',
    'stock_shopify', 'stock_cedis', 'maximos', 'tiene_stock'
]].copy()
df_show['Disponible CEDIS'] = df_show['tiene_stock'].map({1: '✅ SÍ', 0: '❌ NO'})
df_show = df_show.drop(columns=['tiene_stock'])

st.dataframe(
    df_show,
    use_container_width=True,
    hide_index=True,
    column_config={
        "stock_shopify": st.column_config.NumberColumn("Stock Shopify"),
        "stock_cedis": st.column_config.NumberColumn("Stock CEDIS"),
        "maximos": st.column_config.NumberColumn("Máximo"),
    }
)

st.divider()

# Vista con imágenes y pedidos
st.subheader("Vista de Productos con Imagen")

if len(df_filt) == 0:
    st.warning("No hay productos con los filtros actuales.")
else:
    # Paginación simple
    items_per_page = 12
    total_pages = (len(df_filt) - 1) // items_per_page + 1
    page = st.number_input("Página", min_value=1, max_value=total_pages, value=1)
    start = (page - 1) * items_per_page
    end = start + items_per_page
    page_df = df_filt.iloc[start:end]

    cols = st.columns(3)
    for idx, (_, row) in enumerate(page_df.iterrows()):
        with cols[idx % 3]:
            if pd.notna(row['image_src']) and row['image_src']:
                st.image(row['image_src'], use_container_width=True)
            else:
                st.info("Sin imagen")

            st.markdown(f"**{row['nombre']}**")
            st.caption(f"SKU: `{row['sku']}`")
            st.write(f"Color: **{row['color']}** | Talla: **{row['talla']}**")
            st.write(f"Colección: {row['coleccion']}")

            stock_cedis = int(row['stock_cedis'])
            stock_shop = int(row['stock_shopify'])
            maximo = int(row['maximos'])

            if stock_cedis > 0:
                st.success(f"CEDIS: {stock_cedis} | Shopify: {stock_shop}")
            else:
                st.error(f"Sin stock CEDIS | Shopify: {stock_shop}")

            st.caption(f"Máximo sugerido: {maximo}")

            # Formulario de pedido
            with st.expander("Hacer pedido"):
                tipo = "normal" if stock_cedis > 0 else "extra"
                st.write(f"Tipo de pedido: **{tipo.upper()}**")
                cantidad = st.number_input(
                    "Cantidad",
                    min_value=1,
                    max_value=100 if stock_cedis > 0 else 50,
                    value=1,
                    key=f"qty_{row['sku']}"
                )
                cliente = st.text_input("Cliente / Sucursal", key=f"cli_{row['sku']}")
                if st.button("Registrar pedido", key=f"btn_{row['sku']}"):
                    st.success(f"Pedido {tipo} registrado: {cantidad} pza de {row['sku']} para {cliente or 'Sin cliente'}")
                    st.info("En producción esto se guarda en PostgreSQL.")

st.divider()
st.caption("Datos de piloto: Shopify (canal) + CEDIS Vallejo (almacén). Imágenes tomadas de gallantdale.com")
