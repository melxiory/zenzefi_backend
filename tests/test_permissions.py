import pytest
from app.core.permissions import validate_path_access, get_allowed_paths


class TestValidatePathAccess:
    """Tests for path access validation"""

    def test_full_scope_allows_all_paths(self):
        """Full scope allows all paths"""
        assert validate_path_access("certificates/filter", "full") is True
        assert validate_path_access("users/currentUser", "full") is True
        assert validate_path_access("system/version", "full") is True
        assert validate_path_access("any/random/path", "full") is True

    def test_certificates_scope_allows_certificate_paths(self):
        """Certificates_only scope allows /certificates/* paths"""
        assert validate_path_access("certificates/filter", "certificates_only") is True
        assert validate_path_access("certificates/details/123", "certificates_only") is True
        assert validate_path_access("certificates/export/456", "certificates_only") is True
        assert validate_path_access("certificates/import/files", "certificates_only") is True
        assert validate_path_access("certificates/update/789", "certificates_only") is True

    def test_certificates_scope_blocks_other_paths(self):
        """Certificates_only scope blocks non-certificate paths"""
        assert validate_path_access("users/currentUser", "certificates_only") is False
        assert validate_path_access("system/version", "certificates_only") is False
        assert validate_path_access("logs/filter", "certificates_only") is False
        assert validate_path_access("zenzefi/ui/environment", "certificates_only") is False

    def test_path_normalization(self):
        """Paths with leading slash are normalized"""
        assert validate_path_access("/certificates/filter", "certificates_only") is True
        assert validate_path_access("certificates/filter", "certificates_only") is True

    def test_unknown_scope_denies_access(self):
        """Unknown scope denies access"""
        assert validate_path_access("certificates/filter", "unknown_scope") is False


class TestGetAllowedPaths:
    """Tests for getting allowed paths"""

    def test_full_scope_returns_none(self):
        """Full scope returns None (all paths)"""
        assert get_allowed_paths("full") is None

    def test_certificates_scope_returns_patterns(self):
        """Certificates_only scope returns list of patterns"""
        patterns = get_allowed_paths("certificates_only")
        assert patterns is not None
        assert len(patterns) > 0
        assert any("certificates/filter" in p for p in patterns)

    def test_unknown_scope_returns_none(self):
        """Unknown scope returns None"""
        assert get_allowed_paths("unknown") is None
