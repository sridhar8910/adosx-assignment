"""
Management command: python manage.py reconcile

Runs the comparison engine and writes results to the Disagreement table.
Safe to run multiple times (truncates and re-inserts each time).

All output goes through Python's logging module rather than stdout.write()
so log format and destination are controlled by Django's LOGGING setting.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

from reconciliation.reconciler import reconcile_from_db

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Compare System A and System B records and write disagreements to the database"

    def handle(self, *args, **options) -> None:  # type: ignore[override]
        logger.info("reconcile command started")
        count = reconcile_from_db()
        logger.info("reconcile command complete: %d disagreement(s) written", count)
        # Also write to stdout so the terminal shows something when run manually
        self.stdout.write(
            self.style.SUCCESS(f"Done. Found {count} disagreement(s).")
        )
