#!/usr/bin/env python
"""
Development server runner for Zenzefi Backend.
Use this file in PyCharm Run Configuration for easy debugging.
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
