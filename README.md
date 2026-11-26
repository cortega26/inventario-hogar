# Inventario Hogar

Aplicacion de escritorio en Python y Tkinter para registrar articulos del hogar, ubicarlos por caja y mantener una base SQLite sencilla.

## Requisitos

- Python 3.12 o superior
- `pip`

## Instalacion

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[theme]
```

Si prefieres no instalar el tema opcional, usa `pip install -e .`. La interfaz seguira funcionando con el tema base de Tk.

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

## Desarrollo

Ejecutar pruebas:

```bash
python -m unittest -q
```

## Archivos generados en runtime

- `inventory.db`
- `inventory.db-backup.db`
- `inventory.log`
- `__pycache__/`

Estos archivos no deberian versionarse. El CSV incluido puede mantenerse como dato de ejemplo o insumo de importacion.
