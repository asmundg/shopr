#!/usr/bin/env python3
"""Main entry point for shopr."""

import sys
import asyncio
import os
import sentry_sdk
from shopr import main

if __name__ == "__main__":
    # Initialize Sentry for error tracking
    # Set SENTRY_DSN environment variable to enable Sentry integration
    sentry_dsn = os.environ.get("SENTRY_DSN")
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        )

    asyncio.run(main())
