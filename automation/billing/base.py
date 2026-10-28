"""Provider-independent billing adapter contracts.

The existing ``Plan``, ``Subscription`` and ``BillingEvent`` models in
``automation.models`` are reused; adapters only translate provider payloads into
those models.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class BillingError(Exception):
    code = 'billing_error'


class BillingNotConfigured(BillingError):
    code = 'billing_not_configured'


class WebhookVerificationError(BillingError):
    code = 'webhook_verification_failed'


@dataclass(frozen=True)
class CheckoutSession:
    provider: str
    session_id: str
    url: str


@dataclass(frozen=True)
class ProviderEvent:
    provider: str
    event_id: str
    event_type: str
    data: dict[str, Any]


class BillingAdapter(ABC):
    provider = ''

    @abstractmethod
    def create_checkout_session(
        self,
        *,
        customer,
        plan,
        local_subscription,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession:
        raise NotImplementedError

    @abstractmethod
    def parse_webhook(self, payload: bytes, signature: str | None) -> ProviderEvent:
        raise NotImplementedError

    @abstractmethod
    def retrieve_subscription(self, provider_subscription_id: str) -> dict[str, Any]:
        raise NotImplementedError
