"""Execution errors with stable, non-sensitive codes."""

from __future__ import annotations


class AutomationExecutionError(Exception):
    code = 'execution_error'

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class ExecutionRejected(AutomationExecutionError):
    """A trigger was rejected before an execution was accepted."""

    code = 'execution_rejected'


class BillingRequired(ExecutionRejected):
    """No active subscription is available for the customer."""

    code = 'subscription_inactive'


class QuotaExceeded(ExecutionRejected):
    """The plan's monthly execution quota has been exhausted."""

    code = 'quota_exceeded'

    def __init__(self, *, used: int, limit: int, window: str):
        self.used = used
        self.limit = limit
        self.window = window
        super().__init__(f'Monthly execution quota exhausted ({used}/{limit}) for {window}.')


class ExecutionConfigurationError(AutomationExecutionError):
    """The workflow configuration is invalid or references an unapproved action."""

    code = 'invalid_configuration'


class ActionError(AutomationExecutionError):
    """A reviewed action handler failed.

    ``retryable`` must be set deliberately: only transient transport/5xx failures
    should be retried. Authentication/validation errors are terminal.
    """

    code = 'action_failed'

    def __init__(self, message: str, *, code: str | None = None, retryable: bool = False):
        super().__init__(message, code=code)
        self.retryable = retryable


class ExecutionTimeout(AutomationExecutionError):
    code = 'execution_timeout'
