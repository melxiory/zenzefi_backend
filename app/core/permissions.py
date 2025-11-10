"""
Path-based access control for token scopes.

This module defines allowed paths for each scope of access tokens.
"""

import re
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

# Allowed paths for each scope
SCOPE_PERMISSIONS = {
    # Full scope - access to all paths
    "full": None,  # None = all paths allowed

    # Certificates only scope - only /certificates/*
    "certificates_only": [
        # Main certificate operations
        r"^certificates/filter",                              # GET - list/search
        r"^certificates/details/",                            # GET - details {id}
        r"^certificates/export/",                             # GET/POST - export {id}
        r"^certificates/import/",                             # POST - import
        r"^certificates/remove",                              # DELETE - remove
        r"^certificates/restore",                             # POST - restore

        # Certificate testing
        r"^certificates/activeForTesting",                    # GET - list active
        r"^certificates/activeForTesting/activate/",          # POST - activate {id}
        r"^certificates/activeForTesting/deactivate/",        # POST - deactivate {id}
        r"^certificates/activeForTesting/enhanced",           # GET - enhanced info
        r"^certificates/activeForTesting/options/",           # GET - options {id}
        r"^certificates/activeForTesting/usecases/",          # GET - use cases {id}

        # Certificate update and integrity checks
        r"^certificates/update/",                             # POST - update {id}
        r"^certificates/update/cancel",                       # POST - cancel
        r"^certificates/update/metrics",                      # GET - metrics
        r"^certificates/checkSystemIntegrityReport",          # GET - report
        r"^certificates/checkSystemIntegrityLog",             # GET - log
        r"^certificates/checkSystemIntegrityLogExistance",    # GET - log check

        # UI configuration (optional, may be needed for DTS Monaco UI)
        r"^configurations/certificatesColumnOrder",           # GET/POST - column order
        r"^configurations/certificatesColumnVisibility",      # GET/POST - column visibility
    ]
}


def validate_path_access(path: str, scope: str) -> bool:
    """
    Check if a path is allowed for the given scope.

    Args:
        path: Request path (without leading slash), e.g. "certificates/filter"
        scope: Token scope ("full" or "certificates_only")

    Returns:
        True if access is allowed, False otherwise

    Examples:
        >>> validate_path_access("certificates/filter", "certificates_only")
        True

        >>> validate_path_access("users/currentUser", "certificates_only")
        False

        >>> validate_path_access("system/version", "full")
        True
    """
    # Normalize path (remove leading slash if present)
    path = path.lstrip("/")

    # Full scope - access to all paths
    if scope == "full":
        return True

    # Get allowed patterns for scope
    allowed_patterns = SCOPE_PERMISSIONS.get(scope)

    # If scope is unknown - deny access
    if allowed_patterns is None and scope != "full":
        logger.warning(f"Unknown scope: {scope}")
        return False

    # If scope has list of patterns - check match
    if allowed_patterns:
        for pattern in allowed_patterns:
            if re.match(pattern, path):
                logger.debug(f"Path '{path}' matched pattern '{pattern}' for scope '{scope}'")
                return True

    logger.info(f"Path '{path}' not allowed for scope '{scope}'")
    return False


def get_allowed_paths(scope: str) -> Optional[List[str]]:
    """
    Return list of allowed regex patterns for a scope.

    Args:
        scope: Token scope

    Returns:
        List of regex patterns or None for full scope
    """
    return SCOPE_PERMISSIONS.get(scope)
