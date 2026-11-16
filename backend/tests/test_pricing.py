"""Pricing engine: pure unit tests (no database)."""

import json

import pytest

from app.modules.printing.pricing import MAX_TOTAL_UGX, ItemSpec, PricingError, Rule, quote_items


def R(id, kind="PER_PAGE", paper="A4", color="BW", duplex=None, option=None, amount=50):  # noqa: A002
    return Rule(
        id=id,
        kind=kind,
        paper_size=paper,
        color_mode=color,
        duplex=duplex,
        option_key=option,
        amount_ugx=amount,
    )


def S(pages=10, copies=1, paper="A4", color="BW", duplex=False, **options):
    return ItemSpec(
        page_count=pages,
        copies=copies,
        paper_size=paper,
        color_mode=color,
        duplex=duplex,
        options=options,
    )


RULES = [
    R("r-bw", color="BW", amount=50),
    R("r-bw-duplex", color="BW", duplex=True, amount=40),
    R("r-color", color="COLOR", amount=300),
    R("r-a3", paper="A3", color="BW", amount=150),
    R("r-staple", kind="PER_COPY", paper=None, color=None, option="staple", amount=100),
    R("r-binding", kind="PER_ORDER", paper=None, color=None, option="binding", amount=2000),
]


def test_page_price_is_pages_times_copies_times_unit() -> None:
    quote = quote_items(RULES, [S(pages=10, copies=2)])
    assert quote.total_ugx == 10 * 2 * 50
    assert quote.items[0].unit_price_ugx == 50 and quote.items[0].page_rule_id == "r-bw"


def test_colour_and_paper_size_select_different_rules() -> None:
    assert quote_items(RULES, [S(pages=1, color="COLOR")]).total_ugx == 300
    assert quote_items(RULES, [S(pages=1, paper="A3")]).total_ugx == 150


def test_exact_duplex_rule_beats_the_generic_one_and_generic_is_the_fallback() -> None:
    assert quote_items(RULES, [S(pages=10, duplex=True)]).total_ugx == 400  # r-bw-duplex
    assert (
        quote_items(RULES, [S(pages=10, color="COLOR", duplex=True)]).total_ugx == 3000
    )  # r-color has duplex=None


@pytest.mark.parametrize("spec", [S(paper="A5"), S(paper="A3", color="COLOR")])
def test_combinations_the_shop_does_not_offer_are_refused(spec: ItemSpec) -> None:
    with pytest.raises(PricingError) as exc:
        quote_items(RULES, [spec])
    assert exc.value.code == "unsupported_combination"


def test_per_copy_extras_scale_with_copies_and_per_order_extras_are_charged_once() -> None:
    per_copy = quote_items(RULES, [S(pages=2, copies=3, staple=True)])
    assert per_copy.total_ugx == 2 * 3 * 50 + 3 * 100
    once = quote_items(RULES, [S(pages=1, binding=True), S(pages=1, copies=2, binding=True)])
    assert once.total_ugx == (1 * 50) + (1 * 2 * 50) + 2000  # binding appears once, not twice
    assert [line["label"] for line in once.order_lines] == ["binding"]


def test_options_that_are_off_cost_nothing_and_unknown_options_are_refused() -> None:
    assert quote_items(RULES, [S(pages=1, staple=False)]).total_ugx == 50
    with pytest.raises(PricingError) as exc:
        quote_items(RULES, [S(pages=1, laminate=True)])
    assert exc.value.code == "unsupported_option"


@pytest.mark.parametrize(
    ("spec", "code"),
    [
        (S(copies=0), "invalid_copies"),
        (S(copies=101), "invalid_copies"),
        (S(pages=0), "invalid_pages"),
    ],
)
def test_invalid_quantities_are_refused(spec: ItemSpec, code: str) -> None:
    with pytest.raises(PricingError) as exc:
        quote_items(RULES, [spec])
    assert exc.value.code == code


def test_empty_and_oversized_orders_are_refused() -> None:
    with pytest.raises(PricingError) as exc:
        quote_items(RULES, [])
    assert exc.value.code == "empty_order"
    with pytest.raises(PricingError) as exc:
        quote_items([R("big", amount=MAX_TOTAL_UGX)], [S(pages=2)])
    assert exc.value.code == "order_too_large"


def test_snapshot_reproduces_the_price_and_is_plain_json() -> None:
    specs = [
        S(pages=7, copies=2, duplex=True, staple=True),
        S(pages=3, color="COLOR", binding=True),
    ]
    quote = quote_items(RULES, specs)
    snapshot = quote.snapshot(specs)
    assert json.loads(json.dumps(snapshot)) == snapshot  # storable as JSONB

    rebuilt = sum(line["amount_ugx"] for item in snapshot["items"] for line in item["lines"])
    rebuilt += sum(line["amount_ugx"] for line in snapshot["order_lines"])
    assert rebuilt == snapshot["total_ugx"] == quote.total_ugx
    assert snapshot["items"][0]["page_rule_id"] == "r-bw-duplex"
    assert snapshot["items"][0]["options"] == {"staple": True}
    assert all(
        isinstance(line["amount_ugx"], int) for item in snapshot["items"] for line in item["lines"]
    )


def test_changing_the_shops_prices_later_does_not_change_an_existing_snapshot() -> None:
    specs = [S(pages=10)]
    before = quote_items(RULES, specs).snapshot(specs)
    repriced = [R("r-bw", amount=999), *RULES[1:]]
    after = quote_items(repriced, specs).snapshot(specs)
    assert before["total_ugx"] == 500 and after["total_ugx"] == 9990  # a new quote differs...
    assert (
        before["items"][0]["unit_price_ugx"] == 50
    )  # ...the stored one still says what was charged


def test_duplicate_rules_resolve_deterministically() -> None:
    rules = [R("b", amount=70), R("a", amount=60)]
    assert quote_items(rules, [S(pages=1)]).items[0].page_rule_id == "a"
    assert quote_items(list(reversed(rules)), [S(pages=1)]).items[0].page_rule_id == "a"
