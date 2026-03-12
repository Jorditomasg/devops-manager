"""
Domain-specific exceptions for DevOps Manager.
"""

class DevOpsManagerException(Exception):
    """Base exception for all applicaton errors."""
    pass

class ConfigurationError(DevOpsManagerException):
    """Raised when there is an error in configuration files or parsing."""
    pass

class RepositoryDetectionError(DevOpsManagerException):
    """Raised when a repository cannot be analyzed or classified properly."""
    pass

class ProcessExecutionError(DevOpsManagerException):
    """Raised when a subprocess fails to start or crashes unexpectedly."""
    pass

class ProfileLoadError(DevOpsManagerException):
    """Raised when a profile cannot be loaded or applied."""
    pass
