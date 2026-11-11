# Cómo actualizar las existencias diarias (paso a paso)

## Lo más simple (recomendado ahora)

1. Descarga el archivo de existencias (el mismo CSV que me compartiste: `1EXISTENCIAS.csv` o similar).
2. **Renómbralo exactamente a** `existencias.csv`.
3. Ve a tu repositorio de GitHub.
4. Arrastra el nuevo `existencias.csv` y reemplaza el anterior (o sube el archivo).
5. Haz commit (puedes escribir "Actualización existencias").
6. En Render:
   - Si tienes auto-deploy activado, se actualiza solo en 1-2 minutos.
   - Si no, entra al servicio y da **Manual Deploy**.

**No tienes que tocar el código.** Solo reemplazas el archivo de datos.

## Estructura que debe tener tu repositorio

```
tu-repo/
├── app.py
├── existencias.csv          ← este archivo lo reemplazas cada día
├── requirements.txt
└── README.md
```

## Máximos que se aplican automáticamente

- XS → 3 piezas
- S → 6 piezas
- M → 6 piezas
- L → 6 piezas
- XL → 3 piezas
- XXL → 3 piezas

## Alerta más importante

En el sidebar elige:  
**ALERTA: No visible en web pero sí en CEDIS**

Ahí ves exactamente los productos que hay que traspasar de CEDIS Vallejo a Shopify para que vuelvan a estar a la venta.

## Notas

- Las imágenes y la disponibilidad (visible/no visible) se traen en vivo desde gallantdale.com/products.json.
- El catálogo se cachea 1 hora para no saturar la página.
- Si el CSV no está o tiene otro nombre, la app te avisa claramente.
