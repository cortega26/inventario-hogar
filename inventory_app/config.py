from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    """Application configuration with enhanced settings."""

    # Database settings
    DB_PATH: str = "inventory.db"
    DB_TIMEOUT: float = 5.0
    LOG_PATH: str = "inventory.log"
    LOG_MAX_BYTES: int = 1_000_000
    LOG_BACKUP_COUNT: int = 3
    BACKUP_DIR: str = "backups"
    BACKUP_RETENTION: int = 10
    BACKUP_INTERVAL_HOURS: int = 24
    DEFAULT_CSV_IMPORT_PATH: str = "Inventario Cajas - Cajas 1-4.csv"

    # Cache settings
    CACHE_TTL: int = 300  # 5 minutes
    CACHE_TTL_SEARCH: int = 60  # 1 minute for search results
    MAX_CACHE_SIZE: int = 1000

    # UI settings
    WINDOW_SIZE: str = "1180x760"
    MIN_WINDOW_SIZE: tuple[int, int] = (1000, 640)
    FONT_SMALL: int = 9
    FONT_NORMAL: int = 10
    FONT_LARGE: int = 12
    FONT_TITLE: int = 14

    # Search settings
    SEARCH_DEBOUNCE_MS: int = 300
    DEFAULT_QUANTITY: int = 1
    MAX_QUANTITY: int = 1_000_000

    # Treeview settings
    ROWS_PER_PAGE: int = 20
    COLUMN_WIDTH_NAME: int = 320
    COLUMN_WIDTH_BOX: int = 200
    COLUMN_WIDTH_QUANTITY: int = 90
    COLUMN_WIDTH_UPDATED: int = 130

    # Data validation settings
    MAX_NAME_LENGTH: int = 255
    MAX_BOX_LENGTH: int = 100
    MAX_NOTES_LENGTH: int = 1000
