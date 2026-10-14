from django.core.management.base import BaseCommand

from match.timeouts import enforce_expired_clocks


class Command(BaseCommand):
    help = "Ends live chess matches whose active clock has expired."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=500)

    def handle(self, *args, **options):
        count = enforce_expired_clocks(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"Expired {count} timed-out match(es)."))
