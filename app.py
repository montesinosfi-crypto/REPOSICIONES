import streamlit as st
import pandas as pd
import requests
import os

st.set_page_config(page_title="Panel de Inventario - Resurtido", page_icon="📦", layout="wide")
st.title("📦 Panel de Inventario y Resurtido")
st.caption("Almacén central: CEDIS Vallejo | Canal web: Shopify")

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
                        all_variants.append({"sku": sku, "title_shopify": p.get("title"), "image_src": image})
            if len(products) < 250:
                break
            page += 1
        except:
            break
    return pd.DataFrame(all_variants)

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

def load_master():
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
        return None, None, "No se encontró lista_maestra.xlsx"
    df = df_master[["SKU", "DESCRIPCIÓN", "MODELO", "COLOR", "TALLA", "COLECCIÓN", "GENERO", "TIPO"]].copy()
    df = df.rename(columns={"SKU": "sku", "DESCRIPCIÓN": "nombre", "MODELO": "modelo",
                            "COLOR": "color", "TALLA": "talla", "COLECCIÓN": "coleccion",
                            "GENERO": "genero", "TIPO": "tipo"})
    df["sku"] = df["sku"].astype(str).str.strip()
    df["color"] = df["color"].fillna("").astype(str).str.strip().str.upper()
    df["talla"] = df["talla"].fillna("").astype(str).str.strip().str.upper()
    df["coleccion"] = df["coleccion"].fillna("SIN COLECCIÓN").astype(str).str.strip()
    df["nombre_grupo"] = df["nombre"].astype(str).str.replace(r'\s*\(COLOR:.*$', '', regex=True).str.strip()

    df_ex = load_existencias()
    if df_ex is None:
        return None, None, "No se encontró existencias.csv"

    cedis = df_ex[df_ex["SUCURSAL"] == "CEDIS VALLEJO"].groupby("CLAVE_ARTICULO")["Suma de EXISTENCIA"].sum().reset_index()
    cedis = cedis.rename(columns={"CLAVE_ARTICULO": "sku", "Suma de EXISTENCIA": "stock_cedis"})
    df = df.merge(cedis, on="sku", how="left")
    df["stock_cedis"] = df["stock_cedis"].fillna(0).astype(int)

    boutiques = df_ex[df_ex["SUCURSAL"] != "CEDIS VALLEJO"].copy()
    stock_bout = boutiques.groupby(["CLAVE_ARTICULO", "SUCURSAL"])["Suma de EXISTENCIA"].sum().reset_index()
    stock_bout = stock_bout.rename(columns={"CLAVE_ARTICULO": "sku", "Suma de EXISTENCIA": "stock_boutique"})

    with st.spinner("Cargando catálogo..."):
        df_shop = fetch_shopify_catalog()
    df = df.merge(df_shop, on="sku", how="left")
    df["visible_web"] = df["title_shopify"].notna()
    return df, stock_bout, None

df_base, stock_bout, error = load_and_build()
if error:
    st.error(error)
    st.stop()

# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.header("Filtros")
todas_boutiques = sorted(stock_bout["SUCURSAL"].unique().tolist()) if stock_bout is not None else []
boutique_sel = st.sidebar.selectbox("Boutique", ["Todas"] + todas_boutiques)
colecciones = ["Todas"] + sorted(df_base["coleccion"].dropna().unique().tolist())
coleccion_sel = st.sidebar.selectbox("Colección", colecciones)
modelos = ["Todos"] + sorted(df_base["modelo"].dropna().unique().tolist())
modelo_sel = st.sidebar.selectbox("Modelo", modelos)
buscar = st.sidebar.text_input("Buscar")
vista = st.sidebar.radio("Vista", ["Matriz de inventario", "Agrupada por producto", "Resurtido por boutique", "Detalle por SKU"])

df_filt = df_base.copy()
if coleccion_sel != "Todas":
    df_filt = df_filt[df_filt["coleccion"] == coleccion_sel]
if modelo_sel != "Todos":
    df_filt = df_filt[df_filt["modelo"] == modelo_sel]
if buscar:
    mask = df_filt["sku"].str.contains(buscar, case=False, na=False) | \
           df_filt["nombre_grupo"].fillna("").str.contains(buscar, case=False, na=False)
    df_filt = df_filt[mask]

c1, c2 = st.columns(2)
c1.metric("SKUs filtrados", len(df_filt))
c2.metric("Con stock CEDIS", int((df_filt["stock_cedis"] > 0).sum()))
st.divider()

# ============================================================
# VISTA: MATRIZ DE INVENTARIO
# ============================================================
if vista == "Matriz de inventario":
    st.subheader("Matriz de inventario por sucursal")
    st.caption("Filas: producto + colección | Columnas: sucursales | Orden de tallas: XS → XXL")

    # Preparar datos para pivot
    if stock_bout is not None and not stock_bout.empty:
        # Unir stock de boutiques
        df_m = df_filt.merge(stock_bout, on="sku", how="left")
        df_m["stock_boutique"] = df_m["stock_boutique"].fillna(0).astype(int)

        # Pivot: filas = nombre_grupo + coleccion + color + talla, columnas = sucursal
        pivot = df_m.pivot_table(
            index=["nombre_grupo", "coleccion", "color", "talla"],
            columns="SUCURSAL",
            values="stock_boutique",
            aggfunc="sum",
            fill_value=0
        ).reset_index()

        # Ordenar tallas
        pivot["talla_ord"] = pivot["talla"].map({t: i for i, t in enumerate(ORDEN_TALLA)}).fillna(99)
        pivot = pivot.sort_values(["nombre_grupo", "color", "talla_ord"]).drop(columns=["talla_ord"])

        st.dataframe(pivot, use_container_width=True, hide_index=True)
    else:
        st.warning("No hay datos de stock por boutique.")

# ============================================================
# VISTA AGRUPADA
# ============================================================
elif vista == "Agrupada por producto":
    st.subheader("Productos agrupados")
    if boutique_sel == "Todas":
        st.info("Selecciona una boutique para ver stock de sucursal.")
    else:
        clasif = get_clasificacion(boutique_sel)
        st.write(f"**Boutique:** {boutique_sel} | **Clasificación:** {clasif}")
        maximos_txt = " | ".join([f"{t}={m}" for t, m in MAXIMOS[clasif].items()])
        st.caption(f"Máximos {clasif}: {maximos_txt}")

        stock_esta = stock_bout[stock_bout["SUCURSAL"] == boutique_sel][["sku", "stock_boutique"]].copy()
        df_b = df_filt.merge(stock_esta, on="sku", how="left")
        df_b["stock_boutique"] = df_b["stock_boutique"].fillna(0).astype(int)
        df_b["maximo"] = df_b.apply(lambda r: get_maximo(r["sku"], r["nombre"], r["talla"], clasif), axis=1)
        df_b["necesidad"] = (df_b["maximo"] - df_b["stock_boutique"]).clip(lower=0)
        df_b["resurtido"] = df_b[["necesidad", "stock_cedis"]].min(axis=1).astype(int)

        grupos = df_b.groupby("nombre_grupo")
        for nombre in sorted([n for n in grupos.groups.keys() if n]):
            grupo = grupos.get_group(nombre)
            img = grupo["image_src"].dropna().iloc[0] if grupo["image_src"].notna().any() else None
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
                    st.write(f"Sucursal: **{int(grupo['stock_boutique'].sum())}** | CEDIS: **{int(grupo['stock_cedis'].sum())}**")
                    vars_df = grupo[["sku", "color", "talla", "stock_boutique", "stock_cedis", "maximo", "resurtido"]].copy()
                    vars_df["talla_ord"] = vars_df["talla"].map({t: i for i, t in enumerate(ORDEN_TALLA)}).fillna(99)
                    vars_df = vars_df.sort_values(["color", "talla_ord"]).drop(columns=["talla_ord"])
                    st.dataframe(vars_df, hide_index=True, use_container_width=True)
                st.divider()

# ============================================================
# RESURTIDO
# ============================================================
elif vista == "Resurtido por boutique":
    st.subheader("Resurtido sugerido")
    if boutique_sel == "Todas":
        st.info("Selecciona una boutique.")
    else:
        clasif = get_clasificacion(boutique_sel)
        st.write(f"**Clasificación:** {clasif}")
        stock_esta = stock_bout[stock_bout["SUCURSAL"] == boutique_sel][["sku", "stock_boutique"]].copy()
        df_b = df_filt.merge(stock_esta, on="sku", how="left")
        df_b["stock_boutique"] = df_b["stock_boutique"].fillna(0).astype(int)
        df_b["maximo"] = df_b.apply(lambda r: get_maximo(r["sku"], r["nombre"], r["talla"], clasif), axis=1)
        df_b["necesidad"] = (df_b["maximo"] - df_b["stock_boutique"]).clip(lower=0)
        df_b["resurtido"] = df_b[["necesidad", "stock_cedis"]].min(axis=1).astype(int)
        mostrar = df_b[df_b["necesidad"] > 0].copy()
        if mostrar.empty:
            st.success("Al máximo.")
        else:
            st.metric("Piezas a resurtir", int(mostrar["resurtido"].sum()))
            st.dataframe(mostrar[["sku", "nombre_grupo", "coleccion", "color", "talla", "stock_boutique", "maximo", "resurtido", "stock_cedis"]],
                         use_container_width=True, hide_index=True)

else:
    st.subheader("Detalle por SKU")
    st.dataframe(df_filt[["sku", "nombre_grupo", "coleccion", "color", "talla", "stock_cedis", "visible_web"]],
                 use_container_width=True, hide_index=True)

st.divider()
st.caption("Matriz: filas = producto + colección + color + talla | Columnas = sucursales")
