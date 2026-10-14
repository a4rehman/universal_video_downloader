"""
Unit tests for TiDB Cloud Database Integration, Repository Layer,
SQL parameterization, migrations, offline fallback, and security.
"""

import os
import json
import pytest
from unittest.mock import MagicMock, patch

from src.database import (
    get_db_config,
    is_db_configured,
    mask_string,
    get_database_status,
    apply_migrations,
    TiDBConnectionManager,
    CloudHistoryRepository,
    CloudFavoritesRepository,
    CloudSettingsRepository,
    sync_local_to_cloud,
    LOCAL_HIST_FILE,
    LOCAL_FAV_FILE,
)


class TestTiDBConfigurationAndSecurity:
    """Tests configuration loading, masking, and secret protection."""

    def test_default_unconfigured(self, monkeypatch):
        monkeypatch.delenv("TIDB_HOST", raising=False)
        monkeypatch.delenv("TIDB_USER", raising=False)
        monkeypatch.delenv("TIDB_DATABASE", raising=False)
        with patch("src.database._load_env_file", return_value={}):
            assert not is_db_configured()
            cfg = get_db_config()
            assert cfg["host"] == ""
            assert cfg["port"] == 4000
            assert cfg["ssl_mode"] == "REQUIRED"

    def test_env_var_loading(self, monkeypatch):
        monkeypatch.setenv("TIDB_HOST", "gateway01.prod.aws.tidbcloud.com")
        monkeypatch.setenv("TIDB_PORT", "4000")
        monkeypatch.setenv("TIDB_USER", "cluster.root")
        monkeypatch.setenv("TIDB_PASSWORD", "SuperSecret123!")
        monkeypatch.setenv("TIDB_DATABASE", "omnistream_test")
        monkeypatch.setenv("TIDB_SSL_MODE", "REQUIRED")

        cfg = get_db_config()
        assert cfg["host"] == "gateway01.prod.aws.tidbcloud.com"
        assert cfg["port"] == 4000
        assert cfg["user"] == "cluster.root"
        assert cfg["password"] == "SuperSecret123!"
        assert cfg["database"] == "omnistream_test"
        assert is_db_configured()

    def test_mask_string_protects_credentials(self):
        assert mask_string("") == ""
        assert mask_string("short") == "***"
        masked = mask_string("gateway01.us-east-1.prod.aws.tidbcloud.com", show_start=4, show_end=10)
        assert masked == "gate***bcloud.com"
        assert "password" not in masked

    def test_health_check_when_unconfigured(self, monkeypatch):
        monkeypatch.delenv("TIDB_HOST", raising=False)
        with patch("src.database._load_env_file", return_value={}):
            status = get_database_status()
            assert status["status"] == "Not configured"
            assert not status["connected"]
            assert "Local Storage" in status["label"]

    def test_health_check_masks_passwords_on_connection_error(self, monkeypatch):
        monkeypatch.setenv("TIDB_HOST", "bad.host.tidbcloud.com")
        monkeypatch.setenv("TIDB_USER", "user")
        monkeypatch.setenv("TIDB_PASSWORD", "SuperSecretPassword123!")
        monkeypatch.setenv("TIDB_DATABASE", "db")

        with patch("pymysql.connect", side_effect=Exception("Failed with SuperSecretPassword123! in connection string")):
            status = get_database_status()
            assert status["status"] == "Connection failed"
            assert "SuperSecretPassword123!" not in str(status["message"])
            assert "SuperSecretPassword123!" not in str(status["error"])


class TestOfflineFallback:
    """Verifies that history, favorites, and settings operate transparently when TiDB is offline."""

    def test_history_offline_crud(self, tmp_path, monkeypatch):
        test_file = str(tmp_path / "test_hist.json")
        monkeypatch.setattr("src.database.LOCAL_HIST_FILE", test_file)
        monkeypatch.delenv("TIDB_HOST", raising=False)
        with patch("src.database._load_env_file", return_value={}):
            # 1. Add record
            ok = CloudHistoryRepository.add_record(
                url="https://youtube.com/watch?v=test12345",
                title="Test Video Title",
                platform="YouTube",
                format_type="Video",
                resolution="1080p",
                size_str="15 MB",
            )
            assert ok
            assert os.path.exists(test_file)

            # 2. Search record
            records = CloudHistoryRepository.search_records(query="test12345")
            assert len(records) == 1
            assert records[0]["title"] == "Test Video Title"

            # 3. Deduplication on add
            CloudHistoryRepository.add_record(
                url="https://youtube.com/watch?v=test12345",
                title="Updated Title",
                platform="YouTube",
                format_type="Video",
                resolution="720p",
                size_str="10 MB",
            )
            records2 = CloudHistoryRepository.search_records(query="test12345")
            assert len(records2) == 1
            assert records2[0]["title"] == "Updated Title"

            # 4. Delete record
            CloudHistoryRepository.delete_record(records2[0]["id"])
            records3 = CloudHistoryRepository.search_records(query="test12345")
            assert len(records3) == 0

    def test_favorites_offline_crud(self, tmp_path, monkeypatch):
        test_fav = str(tmp_path / "test_fav.json")
        monkeypatch.setattr("src.database.LOCAL_FAV_FILE", test_fav)
        monkeypatch.delenv("TIDB_HOST", raising=False)
        with patch("src.database._load_env_file", return_value={}):
            # 1. Add favorite
            ok = CloudFavoritesRepository.add_favorite(
                url="https://instagram.com/p/test",
                title="Fav Insta",
                platform="Instagram",
            )
            assert ok
            assert os.path.exists(test_fav)

            # 2. Load favorites
            favs = CloudFavoritesRepository.load_favorites()
            assert len(favs) == 1
            assert favs[0]["url"] == "https://instagram.com/p/test"

            # 3. Remove favorite
            CloudFavoritesRepository.remove_favorite(favs[0]["id"])
            assert len(CloudFavoritesRepository.load_favorites()) == 0


class TestMockedTiDBOperations:
    """Verifies parameterized SQL execution and transaction handling using mocked PyMySQL connections."""

    @pytest.fixture
    def mock_db_connection(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.__enter__.return_value = mock_conn
        with patch("src.database.TiDBConnectionManager.get_connection", return_value=mock_conn):
            with patch("src.database.is_db_configured", return_value=True):
                yield mock_conn, mock_cursor

    def test_history_insert_parameterized(self, mock_db_connection, tmp_path, monkeypatch):
        mock_conn, mock_cursor = mock_db_connection
        monkeypatch.setattr("src.database.LOCAL_HIST_FILE", str(tmp_path / "hist.json"))

        CloudHistoryRepository.add_record(
            url="https://tiktok.com/@user/video/123",
            title="Cool TikTok",
            platform="TikTok",
            format_type="Video",
            resolution="Best",
            size_str="5 MB",
        )

        # Verify parameterized SQL statements were executed
        assert mock_cursor.execute.call_count >= 2
        # Verify first call is delete (deduplication) using parameterized query
        first_call = mock_cursor.execute.call_args_list[0]
        assert "DELETE FROM download_history WHERE url = %s" in first_call[0][0]
        assert first_call[0][1] == ("https://tiktok.com/@user/video/123",)

        # Verify second call is insert using parameterized query
        second_call = mock_cursor.execute.call_args_list[1]
        assert "INSERT INTO download_history" in second_call[0][0]
        params = second_call[0][1]
        assert params[1] == "https://tiktok.com/@user/video/123"
        assert params[2] == "Cool TikTok"

    def test_favorites_insert_parameterized(self, mock_db_connection, tmp_path, monkeypatch):
        mock_conn, mock_cursor = mock_db_connection
        monkeypatch.setattr("src.database.LOCAL_FAV_FILE", str(tmp_path / "fav.json"))

        CloudFavoritesRepository.add_favorite(
            url="https://youtube.com/playlist?list=123",
            title="My Playlist",
            platform="YouTube",
        )

        assert mock_cursor.execute.call_count >= 2
        first_call = mock_cursor.execute.call_args_list[0]
        assert "DELETE FROM favorites WHERE url = %s" in first_call[0][0]
        second_call = mock_cursor.execute.call_args_list[1]
        assert "INSERT INTO favorites" in second_call[0][0]
        assert second_call[0][1][1] == "https://youtube.com/playlist?list=123"

    def test_migration_idempotency(self, mock_db_connection):
        mock_conn, mock_cursor = mock_db_connection

        # Scenario 1: Version 1 already applied
        mock_cursor.fetchone.return_value = {"version": 1}
        ok, msg = apply_migrations()
        assert ok
        assert "up to date" in msg

        # Scenario 2: Migration not yet applied
        mock_cursor.fetchone.return_value = None
        ok2, msg2 = apply_migrations()
        assert ok2
        assert "up to date" in msg2
        # Ensure migration table and schemas were executed
        assert mock_cursor.execute.call_count >= 5
