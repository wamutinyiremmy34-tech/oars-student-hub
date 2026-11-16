"""Explicit state machines. Only the transitions listed here are ever allowed."""


class OrderStatus:
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    PRINTING = "PRINTING"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

    ALL = (DRAFT, SUBMITTED, ACCEPTED, PRINTING, READY_FOR_PICKUP, COMPLETED, CANCELLED, REJECTED)
    TERMINAL = frozenset({COMPLETED, CANCELLED, REJECTED})
    # A student may cancel until printing starts.
    STUDENT_CANCELLABLE = frozenset({DRAFT, SUBMITTED, ACCEPTED})


ORDER_TRANSITIONS: dict[str, frozenset[str]] = {
    OrderStatus.DRAFT: frozenset({OrderStatus.SUBMITTED, OrderStatus.CANCELLED}),
    OrderStatus.SUBMITTED: frozenset(
        {OrderStatus.ACCEPTED, OrderStatus.REJECTED, OrderStatus.CANCELLED}
    ),
    OrderStatus.ACCEPTED: frozenset(
        {OrderStatus.PRINTING, OrderStatus.REJECTED, OrderStatus.CANCELLED}
    ),
    OrderStatus.PRINTING: frozenset({OrderStatus.READY_FOR_PICKUP}),
    OrderStatus.READY_FOR_PICKUP: frozenset({OrderStatus.COMPLETED}),
    OrderStatus.COMPLETED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.REJECTED: frozenset(),
}


def can_transition(current: str, target: str) -> bool:
    return target in ORDER_TRANSITIONS.get(current, frozenset())


class PaymentStatus:
    """Used both for payments.status (no UNPAID) and print_orders.payment_status."""

    UNPAID = "UNPAID"
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    ALL = (UNPAID, PENDING, PAID, FAILED, REFUNDED)


# print_orders.payment_status
ORDER_PAYMENT_TRANSITIONS: dict[str, frozenset[str]] = {
    PaymentStatus.UNPAID: frozenset(
        {PaymentStatus.PENDING, PaymentStatus.PAID}
    ),  # PAID directly = cash at pickup
    PaymentStatus.PENDING: frozenset(
        {PaymentStatus.PAID, PaymentStatus.FAILED, PaymentStatus.UNPAID}
    ),
    PaymentStatus.FAILED: frozenset(
        {PaymentStatus.PENDING, PaymentStatus.PAID}
    ),  # a retry, or a late confirmation
    PaymentStatus.PAID: frozenset({PaymentStatus.REFUNDED}),
    PaymentStatus.REFUNDED: frozenset(),
}

# payments.status. FAILED -> PAID exists because a provider can confirm a payment after we gave up waiting
# (always after re-verification with the provider, never from a webhook body alone).
PAYMENT_TRANSITIONS: dict[str, frozenset[str]] = {
    PaymentStatus.PENDING: frozenset({PaymentStatus.PAID, PaymentStatus.FAILED}),
    PaymentStatus.FAILED: frozenset({PaymentStatus.PAID}),
    PaymentStatus.PAID: frozenset({PaymentStatus.REFUNDED}),
    PaymentStatus.REFUNDED: frozenset(),
}


def can_pay_transition(current: str, target: str) -> bool:
    return target in PAYMENT_TRANSITIONS.get(current, frozenset())


def can_order_pay_transition(current: str, target: str) -> bool:
    return target in ORDER_PAYMENT_TRANSITIONS.get(current, frozenset())
