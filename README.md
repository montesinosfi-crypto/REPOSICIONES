# Dashboard de Inventario - Piloto Shopify + CEDIS Vallejo

Sistema de visualización de disponibilidad por línea/color/talla con imágenes de producto y registro de pedidos (normal o extra).

## Contenido

- `schema.sql` — Esquema PostgreSQL
- `productos_piloto.csv` — Dataset limpio unificado (resurtido + existencias + imágenes)
- `app.py` — Dashboard Streamlit
- `requirements.txt`

## Cómo ejecutarlo localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Despliegue gratuito (recomendado)

1. Sube esta carpeta a un repositorio de GitHub.
2. Ve a [share.streamlit.io](https://share.streamlit.io) e inicia sesión con GitHub.
3. Crea una nueva app apuntando al archivo `app.py`.
4. Streamlit Cloud la despliega automáticamente.

## Conexión a PostgreSQL (opcional)

Si quieres persistir pedidos y stock en base de datos:

1. Crea una base gratuita en [Neon.tech](https://neon.tech) o [Supabase](https://supabase.com).
2. Ejecuta `schema.sql`.
3. Usa el script `load_to_postgres.py` (puedes pedírmelo) para cargar `productos_piloto.csv`.

## Piloto actual

- **Canal a monitorear:** SHOPIFY
- **Almacén que surte:** CEDIS VALLEJO
- **Indicador principal:** ¿Hay stock en CEDIS? (SÍ / NO)
- **Imágenes:** tomadas de gallantdale.com por SKU

## Próximos pasos posibles

- Agregar más sucursales al filtro
- Cálculo de rotación de inventarios (requiere movimientos históricos)
- Login de usuarios
- Guardar pedidos reales en PostgreSQL
- Alertas cuando el stock de CEDIS está por debajo del máximo
