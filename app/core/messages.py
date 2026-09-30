"""Centralized application message constants."""

# Request / response messages
INTERNAL_SERVER_ERROR = "Internal server error"

# Logging message templates
LOG_REQUEST_LINE = "%s %s -> %s in %.1fms (client=%s)"
LOG_REQUEST_EXCEPTION_LINE = "%s %s -> unhandled exception after %.1fms (client=%s)"
