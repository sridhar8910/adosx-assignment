"""
Management command: python manage.py reconcile

Runs the comparison engine and writes results to the Disagreement table.
Safe to run multiple times (truncates and re-inserts each time).
"""

from django.core.management.base import BaseCommand

from reconciliation.reconciler import reconcile_from_db


class Command(BaseCommand):
    help = 'Compare System A and System B and write disagreements to the database'

    def handle(self, *args, **options):
        self.stdout.write('Running reconciliation…')
        count = reconcile_from_db()
        self.stdout.write(self.style.SUCCESS(f'Done. Found {count} disagreement(s).'))
