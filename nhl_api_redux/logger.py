"""
Logging for the nhl_api_redux package.

The package never configures logging itself -- it only emits records on the
"nhl_api_redux" logger and attaches a NullHandler so that a host application
that does not care about them sees nothing. To route these records, configure
that logger name from the host app:

    import logging
    logging.getLogger("nhl_api_redux").addHandler(my_handler)

Set NHL_API_LOG_LEVEL (e.g. DEBUG) to raise the package's own level when using
it standalone.
"""

import logging
import os

logger = logging.getLogger("nhl_api_redux")

# Keeps "No handlers could be found" quiet when the host app configures nothing.
logger.addHandler(logging.NullHandler())

_level = os.environ.get("NHL_API_LOG_LEVEL")
if _level:
    logger.setLevel(getattr(logging, _level.upper(), logging.WARNING))
