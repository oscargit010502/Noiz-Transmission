"""Native desktop presentation; the acoustic engine has no Qt dependency."""


def main() -> int:
    """Launch the desktop application, importing Qt only when needed."""
    from .main_window import run

    return run()
