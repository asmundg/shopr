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
            # Set traces_sample_rate to 1.0 to capture 100% of transactions for tracing
            # Adjust this value in production for performance
            traces_sample_rate=1.0,
            # Set profiles_sample_rate to 1.0 to profile 100% of sampled transactions
            # Remove this option if you don't want to use profiling
            profiles_sample_rate=1.0,
            # Capture environment info
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        )

    asyncio.run(main())
