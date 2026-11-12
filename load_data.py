"""
Carga lista_maestra.xlsx + existencias.csv a PostgreSQL.
Ignora SKUs duplicados.
"""
import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("Define DATABASE_URL")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def main():
    print("Leyendo lista maestra...")
    df_m = pd.read_excel("lista_maestra.xlsx")
    df_m.columns = df_m.columns.str.strip()
    df_m["SKU"] = df_m["SKU"].astype(str).str.strip()
    df_m = df_m[df_m["SKU"].notna() & (df_m["SKU"] != "") & (df_m["SKU"] != "nan")].copy()

    duplicados = df_m["SKU"].duplicated().sum()
    if duplicados > 0:
        print(f"Advertencia: se encontraron {duplicados} SKUs duplicados. Se conservará el primero.")
    df_m = df_m.drop_duplicates(subset=["SKU"], keep="first")

    productos = df_m[["SKU", "DESCRIPCIÓN", "LINEA", "COLOR", "TALLA", "COLECCIÓN", "FAMILIA"]].copy()
    productos = productos.rename(columns={
        "SKU": "sku", "DESCRIPCIÓN": "nombre", "LINEA": "linea",
        "COLOR": "color", "TALLA": "talla", "COLECCIÓN": "coleccion", "FAMILIA": "familia"
    })
    productos["color"] = productos["color"].fillna("").astype(str).str.strip().str.upper()
    productos["talla"] = productos["talla"].fillna("").astype(str).str.strip().str.upper()
    productos["coleccion"] = productos["coleccion"].fillna("SIN COLECCIÓN").astype(str).str.strip()
    productos["familia"] = productos["familia"].fillna("").astype(str).str.strip()
    productos["linea"] = productos["linea"].fillna("").astype(str).str.strip()

    print("Leyendo existencias...")
    df_ex = pd.read_csv("existencias.csv", low_memory=False)
    df_ex["CLAVE_ARTICULO"] = df_ex["CLAVE_ARTICULO"].astype(str).str.strip()

    cedis = df_ex[df_ex["SUCURSAL"] == "CEDIS VALLEJO"].groupby("CLAVE_ARTICULO")["Suma de EXISTENCIA"].sum().reset_index()
    cedis = cedis.rename(columns={"CLAVE_ARTICULO": "sku", "Suma de EXISTENCIA": "stock_cedis"})
    productos = productos.merge(cedis, on="sku", how="left")
    productos["stock_cedis"] = productos["stock_cedis"].fillna(0).astype(int)
    productos["image_src"] = None
    productos["visible_web"] = False

    boutiques = df_ex[df_ex["SUCURSAL"] != "CEDIS VALLEJO"].copy()
    stock_b = boutiques.groupby(["CLAVE_ARTICULO", "SUCURSAL"])["Suma de EXISTENCIA"].sum().reset_index()
    stock_b = stock_b.rename(columns={"CLAVE_ARTICULO": "sku", "SUCURSAL": "sucursal", "Suma de EXISTENCIA": "stock"})

    print("Conectando a PostgreSQL...")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("""
        DROP TABLE IF EXISTS productos CASCADE;
        DROP TABLE IF EXISTS stock_boutiques CASCADE;
        CREATE TABLE productos (
            sku TEXT PRIMARY KEY, nombre TEXT, linea TEXT, color TEXT, talla TEXT,
            coleccion TEXT, familia TEXT, stock_cedis INTEGER DEFAULT 0,
            image_src TEXT, visible_web BOOLEAN DEFAULT FALSE
        );
        CREATE TABLE stock_boutiques (
            sku TEXT, sucursal TEXT, stock INTEGER DEFAULT 0, PRIMARY KEY (sku, sucursal)
        );
    """)

    print(f"Insertando {len(productos)} productos...")
    execute_values(cur, """
        INSERT INTO productos (sku, nombre, linea, color, talla, coleccion, familia, stock_cedis, image_src, visible_web)
        VALUES %s
    """, productos[["sku","nombre","linea","color","talla","coleccion","familia","stock_cedis","image_src","visible_web"]].values.tolist())

    print(f"Insertando {len(stock_b)} registros de stock...")
    execute_values(cur, """
        INSERT INTO stock_boutiques (sku, sucursal, stock) VALUES %s
    """, stock_b[["sku","sucursal","stock"]].values.tolist())

    conn.commit()
    cur.close()
    conn.close()
    print("¡Carga completada!")

if __name__ == "__main__":
    main()
