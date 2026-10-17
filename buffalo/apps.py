from django.apps import AppConfig


class BuffaloConfig(AppConfig):
    name = "buffalo"
    verbose_name = "Buffalo records"

    def ready(self) -> None:
        from buffalo import signals  # noqa: F401
