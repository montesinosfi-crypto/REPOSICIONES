"""
Script para cargar productos_piloto.csv a PostgreSQL.
Requiere variable de entorno DATABASE_URL o modificar la conexión abajo.
"""
import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/inventario")

def main():
    df = pd.read_csv("productos_piloto.csv")
    print(f"Cargando {len(df)} productos...")

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    for _, row in df.iterrows():
        cur.execute("""
            INSERT INTO productos (sku, nombre, talla, color, coleccion, maximos, precio, url_imagen, product_url, estado_publico)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (sku) DO UPDATE SET
                nombre = EXCLUDED.nombre,
                talla = EXCLUDED.talla,
                color = EXCLUDED.color,
                coleccion = EXCLUDED.coleccion,
                maximos = EXCLUDED.maximos,
                precio = EXCLUDED.precio,
                url_imagen = EXCLUDED.url_imagen,
                product_url = EXCLUDED.product_url,
                estado_publico = EXCLUDED.estado_publico,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """, (
            row['sku'], row['nombre'], row['talla'], row['color'], row['coleccion'],
            int(row['maximos']) if pd.notna(row['maximos']) else 0,
            float(row['price']) if pd.notna(row['price']) else None,
            row['image_src'] if pd.notna(row['image_src']) else None,
            row['product_url'] if pd.notna(row['product_url']) else None,
            row['estado_publico'] if pd.notna(row['estado_publico']) else None
        ))
        producto_id = cur.fetchone()[0]

        # Stock Shopify
        cur.execute("""
            INSERT INTO stock_sucursal (producto_id, sucursal, cantidad)
            VALUES (%s, 'SHOPIFY', %s)
            ON CONFLICT (producto_id, sucursal) DO UPDATE SET
                cantidad = EXCLUDED.cantidad,
                ultima_actualizacion = CURRENT_TIMESTAMP
        """, (producto_id, int(row['stock_shopify'])))

        # Stock CEDIS
        cur.execute("""
            INSERT INTO stock_sucursal (producto_id, sucursal, cantidad)
            VALUES (%s, 'CEDIS VALLEJO', %s)
            ON CONFLICT (producto_id, sucursal) DO UPDATE SET
                cantidad = EXCLUDED.cantidad,
                ultima_actualizacion = CURRENT_TIMESTAMP
        """, (producto_id, int(row['stock_cedis'])))

    conn.commit()
    cur.close()
    conn.close()
    print("Carga completada.")

if __name__ == "__main__":
    main()
