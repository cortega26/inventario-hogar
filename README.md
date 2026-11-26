# Inventario Hogar

Aplicacion de escritorio en Python y Tkinter para registrar articulos del hogar, ubicarlos por caja y mantener una base SQLite sencilla.

## Requisitos

- Python 3.12 o superior
- `pip`

## Instalacion

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Uso

Ejecutar la aplicacion:

```bash
inventario-hogar
```

Alternativa directa:

```bash
python main.py
```

Importar articulos desde CSV:

```bash
python act_db.py "Inventario Cajas - Cajas 1-4.csv" --db-path inventory.db
```

Reemplazar primero el inventario existente:

```bash
python act_db.py "Inventario Cajas - Cajas 1-4.csv" --db-path inventory.db --replace
```

Validar la base de datos:

```bash
python validation_script.py --db-path inventory.db
```

Migrar o normalizar la base de datos:

```bash
python migrate_db.py --db-path inventory.db
```

## Interfaz

- Busqueda instantanea por nombre, nota o ubicacion.
- Filtro por caja y metricas de articulos, unidades y ubicaciones.
- Panel de detalle para crear o editar sin salir de la lista.
- Atajos: `Ctrl+N` nuevo, `Ctrl+S` guardar, `Ctrl+F` buscar, `Supr` eliminar.

## Exportar

El boton `Exportar` ofrece dos formatos con los articulos visibles (respetando
busqueda y filtro):

- **Excel (.xlsx)**: encabezados con estilo, filtros, panel congelado, anchos de
  columna y fechas con formato. Tambien accesible con `Ctrl+E`.
- **CSV (.csv)**: reporte plano en UTF-8.

La exportacion escapa valores que empiezan con `=`, `+`, `-` o `@` para evitar
inyeccion de formulas al abrir el archivo en una hoja de calculo.

## Respaldos y logs

- Al abrir la app se crea un respaldo automatico como maximo una vez cada 24 horas
  en `backups/` (se conservan los 10 mas recientes).
- `act_db.py --replace` y las migraciones de esquema crean un respaldo previo.
- `inventory.log` rota al superar 1 MB y conserva 3 archivos historicos.

## Desarrollo

Ejecutar pruebas:

```bash
python -m unittest -q
```

## Archivos generados en runtime

- `inventory.db`
- `inventory.db-backup.db`
- `inventory.log`
- `backups/`
- `__pycache__/`

Estos archivos no deberian versionarse. El CSV de inventario real tambien queda fuera del repositorio para no exponer datos personales.
