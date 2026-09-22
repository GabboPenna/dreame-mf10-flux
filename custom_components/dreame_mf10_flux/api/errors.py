"""Safe cloud errors. Copyright 2026 Gabriele Pennacchia."""


class CloudError(Exception):
    """A protocol failure without server response bodies or credentials."""


class AuthenticationError(CloudError):
    """The account requires fresh credentials."""


class Unavailable(CloudError):
    """The service or device is temporarily unavailable."""


class RateLimited(Unavailable):
    """The service requested a pause."""

    def __init__(self, retry_after: float = 60) -> None:
        self.retry_after = retry_after
        super().__init__("Cloud request limit reached")


class CommandError(CloudError):
    """The cloud did not confirm a command."""
