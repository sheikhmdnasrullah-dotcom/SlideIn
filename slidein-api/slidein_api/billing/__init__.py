"""Billing package — prepaid credits, ledger, price book, payments, usage.

Customer-facing model: one credit balance per tenant, derived from an
append-only ledger. Reservations hold credits while a job runs; the final
charge is captured against the reservation and the remainder released.
Nothing here invents provider prices: provider costs are recorded with an
explicit `cost_basis` of `"actual"` or `"estimate"`.
"""

from . import models  # noqa: F401  (register tables on Base before create_all)

__all__ = ["models"]
