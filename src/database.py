"""
TiDB Cloud Database Integration & Persistence Layer for OmniStream.

Provides a robust MySQL-compatible repository with SSL/TLS encryption for TiDB Cloud Serverless,
automatic versioned schema migrations, health checks, parameterized queries,
and graceful offline fallback to local JSON storage.
"""

import os
import ssl
import time
import json
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("omnistream.database")

# Latest schema version
CURRENT_SCHEMA_VERSION = 1


def _load_env_file(filepath: str = ".env") -> Dict[str, str]:
    """Safely loads key-value pairs from a local .env file without modifying os.environ."""
    env_vars: Dict[str, str] = {}
    if not os.path.exists(filepath):
        return env_vars
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k:
                    env_vars[k] = v
    except Exception as exc:
        logger.debug("Failed reading .env file: %s", exc)
    return env_vars


def get_db_config() -> Dict[str, Any]:
    """
    Extracts database configuration from Streamlit secrets, environment variables, or local .env.
    Never returns passwords in logs or user interfaces.
    """
    cfg: Dict[str, Any] = {
        "host": "",
        "port": 4000,
        "user": "",
        "password": "",
        "database": "",
        "ssl_mode": "REQUIRED",
    }

    # 1. Try Streamlit secrets if running inside Streamlit
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            db_sec = st.secrets.get("database", {})
            if db_sec:
                cfg["host"] = str(db_sec.get("host", ""))
                cfg["port"] = int(db_sec.get("port", 4000))
                cfg["user"] = str(db_sec.get("user", ""))
                cfg["password"] = str(db_sec.get("password", ""))
                cfg["database"] = str(db_sec.get("database", ""))
                cfg["ssl_mode"] = str(db_sec.get("ssl_mode", "REQUIRED"))
            else:
                # Flat keys in st.secrets
                if "TIDB_HOST" in st.secrets:
                    cfg["host"] = str(st.secrets["TIDB_HOST"])
                if "TIDB_PORT" in st.secrets:
                    cfg["port"] = int(st.secrets["TIDB_PORT"])
                if "TIDB_USER" in st.secrets:
                    cfg["user"] = str(st.secrets["TIDB_USER"])
                if "TIDB_PASSWORD" in st.secrets:
                    cfg["password"] = str(st.secrets["TIDB_PASSWORD"])
                if "TIDB_DATABASE" in st.secrets:
                    cfg["database"] = str(st.secrets["TIDB_DATABASE"])
                if "TIDB_SSL_MODE" in st.secrets:
                    cfg["ssl_mode"] = str(st.secrets["TIDB_SSL_MODE"])
    except Exception:
        pass

    # 2. Check environment variables
    env_host = os.environ.get("TIDB_HOST")
    if env_host:
        cfg["host"] = env_host
        cfg["port"] = int(os.environ.get("TIDB_PORT", cfg["port"] or 4000))
        cfg["user"] = os.environ.get("TIDB_USER", cfg["user"])
        cfg["password"] = os.environ.get("TIDB_PASSWORD", cfg["password"])
        cfg["database"] = os.environ.get("TIDB_DATABASE", cfg["database"])
        cfg["ssl_mode"] = os.environ.get("TIDB_SSL_MODE", cfg["ssl_mode"])

    # 3. Check local .env file if host still not configured
    if not cfg["host"]:
        local_env = _load_env_file()
        if "TIDB_HOST" in local_env:
            cfg["host"] = local_env["TIDB_HOST"]
            cfg["port"] = int(local_env.get("TIDB_PORT", 4000))
            cfg["user"] = local_env.get("TIDB_USER", "")
            cfg["password"] = local_env.get("TIDB_PASSWORD", "")
            cfg["database"] = local_env.get("TIDB_DATABASE", "")
            cfg["ssl_mode"] = local_env.get("TIDB_SSL_MODE", "REQUIRED")

    return cfg


def is_db_configured() -> bool:
    """Returns True if minimum required TiDB connection parameters are present."""
    cfg = get_db_config()
    return bool(cfg.get("host") and cfg.get("user") and cfg.get("database"))


def mask_string(val: str, show_start: int = 3, show_end: int = 3) -> str:
    """Safely masks sensitive identifiers for diagnostics without exposing credentials."""
    if not val:
        return ""
    if len(val) <= (show_start + show_end):
        return "***"
    return f"{val[:show_start]}***{val[-show_end:]}"


class TiDBConnectionManager:
    """Manages secure TLS connections to TiDB Cloud."""

    @staticmethod
    def get_connection(timeout: int = 5):
        """
        Establishes a secure connection to TiDB Cloud using PyMySQL with TLS.
        Raises RuntimeError if PyMySQL is not installed or if credentials are missing.
        """
        cfg = get_db_config()
        if not cfg["host"] or not cfg["user"] or not cfg["database"]:
            raise ValueError("TiDB database configuration is incomplete.")

        try:
            import pymysql
            import pymysql.cursors
        except ImportError as e:
            raise RuntimeError(
                "PyMySQL driver is not installed. Run 'pip install pymysql cryptography'."
            ) from e

        # Configure SSL context for TiDB Cloud Serverless
        ssl_ctx = ssl.create_default_context()
        if cfg.get("ssl_mode", "REQUIRED").upper() == "DISABLED":
            ssl_arg = None
        else:
            ssl_arg = ssl_ctx

        return pymysql.connect(
            host=cfg["host"],
            port=int(cfg["port"]),
            user=cfg["user"],
            password=cfg["password"],
            database=cfg["database"],
            ssl=ssl_arg,
            connect_timeout=timeout,
            read_timeout=timeout,
            write_timeout=timeout,
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
            charset="utf8mb4",
        )


# =====================================================================
# SCHEMA MIGRATIONS
# =====================================================================

MIGRATION_V1_SQL = [
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INT PRIMARY KEY,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        description VARCHAR(255) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS download_history (
        id VARCHAR(64) PRIMARY KEY,
        url VARCHAR(1024) NOT NULL,
        title VARCHAR(512) DEFAULT 'Downloaded Media',
        platform VARCHAR(64) DEFAULT 'Web',
        format_type VARCHAR(32) DEFAULT 'Video',
        resolution VARCHAR(64) DEFAULT 'Best',
        size_str VARCHAR(64) DEFAULT '?',
        file_path VARCHAR(1024) DEFAULT '',
        thumbnail VARCHAR(1024) DEFAULT '',
        status VARCHAR(32) DEFAULT 'Completed',
        downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_timestamp DOUBLE NOT NULL,
        INDEX idx_hist_url (url(255)),
        INDEX idx_hist_platform (platform),
        INDEX idx_hist_time (created_timestamp)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS favorites (
        id VARCHAR(64) PRIMARY KEY,
        url VARCHAR(1024) NOT NULL UNIQUE,
        title VARCHAR(512) DEFAULT '',
        name VARCHAR(512) DEFAULT '',
        platform VARCHAR(64) DEFAULT 'Web',
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_timestamp DOUBLE NOT NULL,
        INDEX idx_fav_platform (platform)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS user_settings (
        setting_key VARCHAR(128) PRIMARY KEY,
        setting_value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
]


def apply_migrations() -> Tuple[bool, str]:
    """
    Applies any pending migrations idempotently.
    Returns (success: bool, message: str).
    """
    if not is_db_configured():
        return False, "Database not configured."

    try:
        with TiDBConnectionManager.get_connection() as conn:
            with conn.cursor() as cur:
                # Ensure migration table exists
                cur.execute(MIGRATION_V1_SQL[0])
                cur.execute("SELECT version FROM schema_migrations WHERE version = 1")
                row = cur.fetchone()

                if not row:
                    # Apply V1
                    for stmt in MIGRATION_V1_SQL[1:]:
                        cur.execute(stmt)
                    cur.execute(
                        "INSERT INTO schema_migrations (version, description) VALUES (%s, %s)",
                        (1, "Initial schema: download_history, favorites, user_settings"),
                    )
            conn.commit()
            return True, "Migrations up to date (Version 1)."
    except Exception as exc:
        sanitized_err = str(exc).split("password")[0]  # Ensure passwords never leaked
        logger.error("Migration failed: %s", sanitized_err)
        return False, f"Migration failed: {sanitized_err}"


def get_schema_version() -> int:
    """Returns the highest applied migration version or 0."""
    if not is_db_configured():
        return 0
    try:
        with TiDBConnectionManager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT MAX(version) AS max_v FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() AND table_name = 'schema_migrations'"
                )
                if not cur.fetchone():
                    return 0
                cur.execute("SELECT MAX(version) AS max_ver FROM schema_migrations")
                row = cur.fetchone()
                return int(row["max_ver"]) if row and row.get("max_ver") else 0
    except Exception:
        return 0


# =====================================================================
# HEALTH CHECK & STATUS
# =====================================================================

def get_database_status() -> Dict[str, Any]:
    """
    Performs a thorough health check of TiDB Cloud.
    Returns structured status without exposing secrets.
    """
    cfg = get_db_config()
    if not is_db_configured():
        return {
            "status": "Not configured",
            "connected": False,
            "host": "",
            "database": "",
            "version": 0,
            "label": "Not configured (Using Local Storage)",
            "message": "TiDB Cloud credentials not set. Falling back to local JSON files.",
            "error": None,
        }

    masked_host = mask_string(cfg.get("host", ""), 4, 10)
    db_name = cfg.get("database", "")

    try:
        with TiDBConnectionManager.get_connection(timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS alive")
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() AND table_name = 'schema_migrations'"
                )
                tbl_row = cur.fetchone()
                has_migration_tbl = tbl_row and tbl_row["cnt"] > 0
                version = 0
                if has_migration_tbl:
                    cur.execute("SELECT MAX(version) AS max_ver FROM schema_migrations")
                    v_row = cur.fetchone()
                    version = int(v_row["max_ver"]) if v_row and v_row.get("max_ver") else 0

        if version < CURRENT_SCHEMA_VERSION:
            return {
                "status": "Migration required",
                "connected": True,
                "host": masked_host,
                "database": db_name,
                "version": version,
                "label": f"Migration Required (v{version} -> v{CURRENT_SCHEMA_VERSION})",
                "message": "Database connected but tables need migration.",
                "error": None,
            }

        return {
            "status": "Connected",
            "connected": True,
            "host": masked_host,
            "database": db_name,
            "version": version,
            "label": f"Connected to TiDB ({masked_host})",
            "message": "Connected to TiDB Cloud Serverless.",
            "error": None,
        }
    except Exception as exc:
        err_msg = str(exc)
        # Strip potential password leak from exception message
        safe_msg = err_msg.replace(cfg.get("password", "___"), "***") if cfg.get("password") else err_msg
        return {
            "status": "Connection failed",
            "connected": False,
            "host": masked_host,
            "database": db_name,
            "version": 0,
            "label": "Connection failed (Using Local Storage)",
            "message": f"Unable to reach TiDB Cloud: {safe_msg[:120]}",
            "error": safe_msg[:200],
        }


# =====================================================================
# DATA REPOSITORIES (WITH AUTOMATIC OFFLINE FALLBACK)
# =====================================================================

class CloudHistoryRepository:
    """Manages download history records in TiDB Cloud with local fallback."""

    @staticmethod
    def add_record(
        url: str,
        title: str,
        platform: str,
        format_type: str,
        resolution: str,
        size_str: str,
        file_path: Optional[str] = None,
        thumbnail: Optional[str] = None,
        status: str = "Completed"
    ) -> bool:
        rec_id = f"hist_{int(time.time()*1000)}"
        now_ts = time.time()

        if is_db_configured():
            try:
                with TiDBConnectionManager.get_connection() as conn:
                    with conn.cursor() as cur:
                        # Deduplicate by URL: delete any existing record for same URL
                        cur.execute("DELETE FROM download_history WHERE url = %s", (url,))
                        cur.execute(
                            """
                            INSERT INTO download_history
                            (id, url, title, platform, format_type, resolution, size_str, file_path, thumbnail, status, created_timestamp)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (rec_id, url, title or "Downloaded Media", platform or "Web",
                             format_type or "Video", resolution or "Best", size_str or "?",
                             file_path or "", thumbnail or "", status, now_ts)
                        )
                # Keep local JSON in sync as offline cache
                _save_local_history_record(rec_id, url, title, platform, format_type, resolution, size_str, file_path, thumbnail, status, now_ts)
                return True
            except Exception as e:
                logger.warning("TiDB write failed, falling back to local JSON: %s", e)

        # Fallback to local storage
        return _save_local_history_record(rec_id, url, title, platform, format_type, resolution, size_str, file_path, thumbnail, status, now_ts)

    @staticmethod
    def search_records(
        query: str = "",
        platform_filter: str = "All",
        type_filter: str = "All",
        sort_by: str = "Newest",
        limit: int = 500
    ) -> List[Dict[str, Any]]:
        if is_db_configured():
            try:
                with TiDBConnectionManager.get_connection() as conn:
                    with conn.cursor() as cur:
                        conditions = []
                        params = []

                        if query:
                            conditions.append("(LOWER(title) LIKE %s OR LOWER(url) LIKE %s OR LOWER(platform) LIKE %s)")
                            q_like = f"%{query.lower()}%"
                            params.extend([q_like, q_like, q_like])

                        if platform_filter and platform_filter != "All":
                            conditions.append("LOWER(platform) = %s")
                            params.append(platform_filter.lower())

                        if type_filter and type_filter != "All":
                            conditions.append("LOWER(format_type) = %s")
                            params.append(type_filter.lower())

                        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

                        order_clause = "ORDER BY created_timestamp DESC"
                        if sort_by == "Oldest":
                            order_clause = "ORDER BY created_timestamp ASC"
                        elif sort_by == "Title (A-Z)":
                            order_clause = "ORDER BY LOWER(title) ASC"

                        sql = f"""
                            SELECT id, url, title, platform, format_type AS format,
                                   resolution, size_str AS size, file_path, thumbnail,
                                   status, DATE_FORMAT(downloaded_at, '%%Y-%%m-%%d %%H:%%i:%%s') AS date,
                                   created_timestamp AS timestamp
                            FROM download_history
                            {where_clause}
                            {order_clause}
                            LIMIT %s
                        """
                        params.append(limit)
                        cur.execute(sql, tuple(params))
                        rows = cur.fetchall()
                        return list(rows)
            except Exception as e:
                logger.warning("TiDB query failed, falling back to local history: %s", e)

        # Fallback to local search
        return _search_local_history(query, platform_filter, type_filter, sort_by)

    @staticmethod
    def delete_record(record_id: str) -> bool:
        if is_db_configured():
            try:
                with TiDBConnectionManager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM download_history WHERE id = %s OR url = %s", (record_id, record_id))
            except Exception as e:
                logger.warning("TiDB delete failed: %s", e)
        # Always remove from local JSON cache as well
        return _delete_local_history(record_id)

    @staticmethod
    def clear_all() -> bool:
        if is_db_configured():
            try:
                with TiDBConnectionManager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("TRUNCATE TABLE download_history")
            except Exception as e:
                logger.warning("TiDB truncate failed: %s", e)
        return _clear_local_history()


class CloudFavoritesRepository:
    """Manages favorite links in TiDB Cloud with local fallback."""

    @staticmethod
    def add_favorite(url: str, title: str, platform: str = "Web", name: str = "") -> bool:
        if not url:
            return False
        fav_id = f"fav_{int(time.time()*1000)}"
        now_ts = time.time()

        if is_db_configured():
            try:
                with TiDBConnectionManager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM favorites WHERE url = %s", (url,))
                        cur.execute(
                            """
                            INSERT INTO favorites (id, url, title, name, platform, created_timestamp)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (fav_id, url, title or url, name or title or url, platform or "Web", now_ts)
                        )
                _save_local_favorite(fav_id, url, title, platform, name, now_ts)
                return True
            except Exception as e:
                logger.warning("TiDB add favorite failed, falling back to local: %s", e)

        return _save_local_favorite(fav_id, url, title, platform, name, now_ts)

    @staticmethod
    def load_favorites() -> List[Dict[str, Any]]:
        if is_db_configured():
            try:
                with TiDBConnectionManager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT id, url, title, name, platform,
                                   DATE_FORMAT(added_at, '%%Y-%%m-%%d %%H:%%i:%%s') AS added_at,
                                   created_timestamp AS timestamp
                            FROM favorites
                            ORDER BY created_timestamp DESC
                            """
                        )
                        return list(cur.fetchall())
            except Exception as e:
                logger.warning("TiDB load favorites failed, using local: %s", e)
        return _load_local_favorites()

    @staticmethod
    def remove_favorite(fav_id_or_url: str) -> bool:
        if is_db_configured():
            try:
                with TiDBConnectionManager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM favorites WHERE id = %s OR url = %s", (fav_id_or_url, fav_id_or_url))
            except Exception as e:
                logger.warning("TiDB remove favorite failed: %s", e)
        return _remove_local_favorite(fav_id_or_url)

    @staticmethod
    def clear_all() -> bool:
        if is_db_configured():
            try:
                with TiDBConnectionManager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("TRUNCATE TABLE favorites")
            except Exception as e:
                logger.warning("TiDB clear favorites failed: %s", e)
        return _clear_local_favorites()


class CloudSettingsRepository:
    """Manages cloud application settings in TiDB Cloud with local fallback."""

    @staticmethod
    def get_setting(key: str, default: Any = None) -> Any:
        if is_db_configured():
            try:
                with TiDBConnectionManager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT setting_value FROM user_settings WHERE setting_key = %s", (key,))
                        row = cur.fetchone()
                        if row and row.get("setting_value") is not None:
                            try:
                                return json.loads(row["setting_value"])
                            except Exception:
                                return row["setting_value"]
            except Exception as e:
                logger.debug("TiDB get_setting failed: %s", e)
        return None

    @staticmethod
    def save_setting(key: str, value: Any) -> bool:
        # Machine-specific settings like download directory should stay local
        if key in ("download_path", "download_dir"):
            return True

        if is_db_configured():
            try:
                val_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
                with TiDBConnectionManager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO user_settings (setting_key, setting_value)
                            VALUES (%s, %s)
                            ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
                            """,
                            (key, val_str)
                        )
                return True
            except Exception as e:
                logger.warning("TiDB save_setting failed: %s", e)
        return False


# =====================================================================
# LOCAL FILE HELPERS (FOR OFFLINE FALLBACK & CACHING)
# =====================================================================

LOCAL_HIST_FILE = os.path.join(os.path.expanduser("~"), ".omnistream_history.json")
LOCAL_FAV_FILE = os.path.join(os.path.expanduser("~"), ".omnistream_favorites.json")


def _load_local_history() -> List[Dict[str, Any]]:
    if not os.path.exists(LOCAL_HIST_FILE):
        return []
    try:
        with open(LOCAL_HIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_local_history_record(rec_id: str, url: str, title: str, platform: str,
                               format_type: str, resolution: str, size_str: str,
                               file_path: Optional[str], thumbnail: Optional[str],
                               status: str, timestamp: float) -> bool:
    try:
        records = _load_local_history()
        records = [r for r in records if r.get("url") != url]
        new_entry = {
            "id": rec_id,
            "url": url,
            "title": title or "Downloaded Media",
            "platform": platform or "Web",
            "format": format_type or "Video",
            "resolution": resolution or "Best",
            "size": size_str or "?",
            "file_path": file_path or "",
            "thumbnail": thumbnail or "",
            "date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)),
            "timestamp": timestamp,
            "status": status,
        }
        records.insert(0, new_entry)
        with open(LOCAL_HIST_FILE, "w", encoding="utf-8") as f:
            json.dump(records[:500], f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def _search_local_history(query: str, platform: str, fmt: str, sort_by: str) -> List[Dict[str, Any]]:
    records = _load_local_history()
    if query:
        q = query.lower()
        records = [r for r in records if q in r.get("title", "").lower() or q in r.get("url", "").lower() or q in r.get("platform", "").lower()]
    if platform and platform != "All":
        records = [r for r in records if r.get("platform", "").lower() == platform.lower()]
    if fmt and fmt != "All":
        records = [r for r in records if r.get("format", "").lower() == fmt.lower()]
    if sort_by == "Newest":
        records.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    elif sort_by == "Oldest":
        records.sort(key=lambda x: x.get("timestamp", 0))
    elif sort_by == "Title (A-Z)":
        records.sort(key=lambda x: x.get("title", "").lower())
    return records


def _delete_local_history(record_id: str) -> bool:
    try:
        records = _load_local_history()
        updated = [r for r in records if r.get("id") != record_id and r.get("url") != record_id]
        with open(LOCAL_HIST_FILE, "w", encoding="utf-8") as f:
            json.dump(updated, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def _clear_local_history() -> bool:
    try:
        with open(LOCAL_HIST_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)
        return True
    except Exception:
        return False


def _load_local_favorites() -> List[Dict[str, Any]]:
    if not os.path.exists(LOCAL_FAV_FILE):
        return []
    try:
        with open(LOCAL_FAV_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_local_favorite(fav_id: str, url: str, title: str, platform: str, name: str, timestamp: float) -> bool:
    try:
        favs = _load_local_favorites()
        favs = [f for f in favs if f.get("url") != url]
        new_fav = {
            "id": fav_id,
            "url": url,
            "title": title or url,
            "name": name or title or url,
            "platform": platform or "Web",
            "added_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)),
            "timestamp": timestamp,
        }
        favs.insert(0, new_fav)
        with open(LOCAL_FAV_FILE, "w", encoding="utf-8") as f:
            json.dump(favs, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def _remove_local_favorite(fav_id_or_url: str) -> bool:
    try:
        favs = _load_local_favorites()
        updated = [f for f in favs if f.get("id") != fav_id_or_url and f.get("url") != fav_id_or_url]
        with open(LOCAL_FAV_FILE, "w", encoding="utf-8") as f:
            json.dump(updated, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def _clear_local_favorites() -> bool:
    try:
        with open(LOCAL_FAV_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)
        return True
    except Exception:
        return False


def sync_local_to_cloud() -> Tuple[int, int]:
    """
    Idempotently syncs existing local JSON download history and favorites to TiDB Cloud.
    Returns (synced_history_count, synced_favorites_count).
    """
    if not is_db_configured():
        return 0, 0

    h_synced = 0
    f_synced = 0

    try:
        apply_migrations()
        with TiDBConnectionManager.get_connection() as conn:
            with conn.cursor() as cur:
                # Sync history
                for h in _load_local_history():
                    url = h.get("url")
                    if not url:
                        continue
                    cur.execute("SELECT id FROM download_history WHERE url = %s", (url,))
                    if not cur.fetchone():
                        cur.execute(
                            """
                            INSERT INTO download_history
                            (id, url, title, platform, format_type, resolution, size_str, file_path, thumbnail, status, created_timestamp)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (h.get("id", f"hist_{int(time.time()*1000)}"), url,
                             h.get("title", "Media"), h.get("platform", "Web"),
                             h.get("format", "Video"), h.get("resolution", "Best"),
                             h.get("size", "?"), h.get("file_path", ""),
                             h.get("thumbnail", ""), h.get("status", "Completed"),
                             h.get("timestamp", time.time()))
                        )
                        h_synced += 1

                # Sync favorites
                for fav in _load_local_favorites():
                    url = fav.get("url")
                    if not url:
                        continue
                    cur.execute("SELECT id FROM favorites WHERE url = %s", (url,))
                    if not cur.fetchone():
                        cur.execute(
                            """
                            INSERT INTO favorites (id, url, title, name, platform, created_timestamp)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (fav.get("id", f"fav_{int(time.time()*1000)}"), url,
                             fav.get("title", url), fav.get("name", url),
                             fav.get("platform", "Web"), fav.get("timestamp", time.time()))
                        )
                        f_synced += 1
        return h_synced, f_synced
    except Exception as e:
        logger.error("Sync to cloud failed: %s", e)
        return h_synced, f_synced
