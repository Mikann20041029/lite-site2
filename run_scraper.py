#!/usr/bin/env python3
"""
Entry point for the Upwork Job Scraper.

Usage:
    python run_scraper.py

Or schedule with cron:
    0 8 * * * cd /path/to/lite-site2 && python run_scraper.py >> logs/scraper.log 2>&1
"""
from upwork_scraper.main import run

if __name__ == "__main__":
    run()
