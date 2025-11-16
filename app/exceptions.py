"""
Custom exceptions for Zenzefi Backend

This module defines application-specific exceptions that can be raised
throughout the application to handle specific error scenarios.
"""


class DeviceConflictError(Exception):
    """
    Raised when an access token is already in use on a different device.

    This exception is thrown when a user attempts to use an access token
    from a device that differs from the device currently using that token.

    The backend enforces a "1 token = 1 device" policy to prevent concurrent
    usage of the same token across multiple devices.

    Example:
        >>> if active_session.device_id != device_id:
        ...     raise DeviceConflictError(
        ...         f"Token already in use on device {active_session.device_id}"
        ...     )
    """
    pass
