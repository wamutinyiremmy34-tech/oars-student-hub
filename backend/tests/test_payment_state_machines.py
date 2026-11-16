"""Order and payment state machines: exhaustive, pure unit tests."""

import itertools

import pytest

from app.modules.printing.state import (
    ORDER_TRANSITIONS,
    OrderStatus,
    PaymentStatus,
    can_order_pay_transition,
    can_pay_transition,
    can_transition,
)

S = OrderStatus


def test_the_table_covers_every_status_and_only_known_ones() -> None:
    assert set(ORDER_TRANSITIONS) == set(S.ALL)
    assert all(targets <= set(S.ALL) for targets in ORDER_TRANSITIONS.values())


def test_every_pair_matches_the_table() -> None:
    for a, b in itertools.product(S.ALL, S.ALL):
        assert can_transition(a, b) == (b in ORDER_TRANSITIONS[a]), (a, b)


def test_the_happy_path_is_allowed_step_by_step() -> None:
    path = [S.DRAFT, S.SUBMITTED, S.ACCEPTED, S.PRINTING, S.READY_FOR_PICKUP, S.COMPLETED]
    assert all(can_transition(a, b) for a, b in itertools.pairwise(path))


@pytest.mark.parametrize("terminal", sorted(S.TERMINAL))
def test_terminal_states_are_final(terminal: str) -> None:
    assert ORDER_TRANSITIONS[terminal] == frozenset()
    assert not any(can_transition(terminal, other) for other in S.ALL)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (S.DRAFT, S.ACCEPTED), (S.DRAFT, S.COMPLETED), (S.SUBMITTED, S.PRINTING), (S.SUBMITTED, S.COMPLETED),
        (S.ACCEPTED, S.READY_FOR_PICKUP), (S.PRINTING, S.COMPLETED), (S.PRINTING, S.CANCELLED),
        (S.PRINTING, S.REJECTED), (S.READY_FOR_PICKUP, S.PRINTING), (S.READY_FOR_PICKUP, S.CANCELLED),
        (S.SUBMITTED, S.DRAFT), (S.ACCEPTED, S.SUBMITTED), (S.COMPLETED, S.PRINTING),
    ],
)  # fmt: skip
def test_skipping_and_going_backwards_are_forbidden(a: str, b: str) -> None:
    assert not can_transition(a, b)


def test_nothing_transitions_to_itself() -> None:
    assert not any(can_transition(s, s) for s in S.ALL)


def test_students_can_only_cancel_before_printing_starts() -> None:
    assert S.STUDENT_CANCELLABLE == {S.DRAFT, S.SUBMITTED, S.ACCEPTED}
    assert all(can_transition(s, S.CANCELLED) for s in S.STUDENT_CANCELLABLE)
    assert S.PRINTING not in S.STUDENT_CANCELLABLE


def test_every_status_is_reachable_from_draft() -> None:
    seen, frontier = {S.DRAFT}, [S.DRAFT]
    while frontier:
        for nxt in ORDER_TRANSITIONS[frontier.pop()]:
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    assert seen == set(S.ALL)


# --------------------------------------------------------------------------- payments

P = PaymentStatus


def test_payment_row_transitions() -> None:
    assert can_pay_transition(P.PENDING, P.PAID)
    assert can_pay_transition(P.PENDING, P.FAILED)
    assert can_pay_transition(
        P.FAILED, P.PAID
    )  # late provider confirmation (after re-verification)
    assert can_pay_transition(P.PAID, P.REFUNDED)
    for forbidden in [
        (P.PAID, P.PENDING),
        (P.PAID, P.FAILED),
        (P.REFUNDED, P.PAID),
        (P.REFUNDED, P.PENDING),
        (P.PENDING, P.REFUNDED),
        (P.FAILED, P.PENDING),
        (P.PAID, P.PAID),
    ]:
        assert not can_pay_transition(*forbidden), forbidden


def test_a_refunded_payment_is_final() -> None:
    assert not any(can_pay_transition(P.REFUNDED, p) for p in P.ALL)


def test_order_payment_state_transitions() -> None:
    assert can_order_pay_transition(P.UNPAID, P.PENDING)
    assert can_order_pay_transition(P.UNPAID, P.PAID)  # cash at pickup
    assert can_order_pay_transition(P.PENDING, P.PAID)
    assert can_order_pay_transition(P.PENDING, P.FAILED)
    assert can_order_pay_transition(P.FAILED, P.PENDING)  # student retries
    assert can_order_pay_transition(P.PAID, P.REFUNDED)
    for forbidden in [
        (P.PAID, P.UNPAID),
        (P.PAID, P.FAILED),
        (P.PAID, P.PENDING),
        (P.REFUNDED, P.PAID),
        (P.UNPAID, P.REFUNDED),
        (P.UNPAID, P.FAILED),
    ]:
        assert not can_order_pay_transition(*forbidden), forbidden
