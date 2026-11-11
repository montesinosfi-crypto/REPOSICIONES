-- ============================================================
-- ESQUEMA POSTGRESQL - INVENTARIO ROTACIÓN + PEDIDOS
-- Piloto: Shopify (canal) + CEDIS Vallejo (almacén)
-- ============================================================

CREATE TABLE IF NOT EXISTS productos (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(80) UNIQUE NOT NULL,
    nombre TEXT,
    talla VARCHAR(30),
    color VARCHAR(60),
    coleccion VARCHAR(100),
    linea VARCHAR(100),
    meli VARCHAR(20),
    amazon VARCHAR(20),
    maximos INTEGER DEFAULT 0,
    precio NUMERIC(12,2),
    url_imagen TEXT,
    product_url TEXT,
    estado_publico VARCHAR(30),
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stock_sucursal (
    id SERIAL PRIMARY KEY,
    producto_id INTEGER REFERENCES productos(id) ON DELETE CASCADE,
    sucursal VARCHAR(100) NOT NULL,
    cantidad INTEGER NOT NULL DEFAULT 0,
    ultima_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(producto_id, sucursal)
);

CREATE TABLE IF NOT EXISTS pedidos (
    id SERIAL PRIMARY KEY,
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('normal', 'extra')),
    canal VARCHAR(50) DEFAULT 'SHOPIFY',
    sucursal_origen VARCHAR(100) DEFAULT 'CEDIS VALLEJO',
    cliente VARCHAR(200),
    estado VARCHAR(30) DEFAULT 'pendiente',
    observaciones TEXT,
    fecha_pedido TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS detalle_pedidos (
    id SERIAL PRIMARY KEY,
    pedido_id INTEGER REFERENCES pedidos(id) ON DELETE CASCADE,
    producto_id INTEGER REFERENCES productos(id),
    sku VARCHAR(80),
    cantidad INTEGER NOT NULL,
    precio_unitario NUMERIC(12,2),
    subtotal NUMERIC(12,2)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_productos_sku ON productos(sku);
CREATE INDEX IF NOT EXISTS idx_productos_linea_color_talla ON productos(coleccion, color, talla);
CREATE INDEX IF NOT EXISTS idx_stock_sucursal ON stock_sucursal(sucursal, producto_id);

-- Vista principal para el dashboard
CREATE OR REPLACE VIEW v_disponibilidad AS
SELECT 
    p.id,
    p.sku,
    p.nombre,
    p.talla,
    p.color,
    p.coleccion,
    p.maximos,
    p.precio,
    p.url_imagen,
    p.product_url,
    p.estado_publico,
    COALESCE(ss.cantidad, 0) AS stock_shopify,
    COALESCE(sc.cantidad, 0) AS stock_cedis,
    CASE WHEN COALESCE(sc.cantidad, 0) > 0 THEN 'SÍ' ELSE 'NO' END AS tiene_stock_cedis,
    CASE 
        WHEN COALESCE(sc.cantidad, 0) >= p.maximos THEN 'OK'
        WHEN COALESCE(sc.cantidad, 0) > 0 THEN 'BAJO'
        ELSE 'SIN STOCK'
    END AS estado_stock
FROM productos p
LEFT JOIN stock_sucursal ss ON p.id = ss.producto_id AND ss.sucursal = 'SHOPIFY'
LEFT JOIN stock_sucursal sc ON p.id = sc.producto_id AND sc.sucursal = 'CEDIS VALLEJO'
WHERE p.activo = TRUE;
