"""Server-side pricing. Pure functions: no database, no framework, easy to test exhaustively.

Rule kinds (all amounts are integer UGX):
  PER_PAGE   price of one printed page for a (paper size, colour mode[, duplex]) combination
  PER_COPY   extra charged per copy when an option is requested (e.g. staple)
  PER_ORDER  extra charged once per order when any item requests the option (e.g. binding)

A quote carries the rule ids and amounts it used, so the exact price can be reproduced later even if the
shop changes its prices.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

MAX_COPIES = 100
MAX_TOTAL_UGX = 50_000_000


class PricingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Rule:
    id: str
    kind: str
    paper_size: str | None
    color_mode: str | None
    duplex: bool | None
    option_key: str | None
    amount_ugx: int


@dataclass(frozen=True)
class ItemSpec:
    page_count: int
    copies: int
    paper_size: str
    color_mode: str
    duplex: bool
    options: Mapping[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class ItemQuote:
    unit_price_ugx: int
    line_total_ugx: int
    page_rule_id: str
    lines: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class Quote:
    items: tuple[ItemQuote, ...]
    order_lines: tuple[dict[str, Any], ...]
    total_ugx: int

    def snapshot(self, specs: Sequence[ItemSpec]) -> dict[str, Any]:
        """Everything needed to reproduce this price, stored on the order."""
        return {
            "currency": "UGX",
            "total_ugx": self.total_ugx,
            "items": [
                {
                    "index": i,
                    "page_count": s.page_count, "copies": s.copies, "paper_size": s.paper_size,
                    "color_mode": s.color_mode, "duplex": s.duplex,
                    "options": {k: v for k, v in sorted(s.options.items()) if v},
                    "unit_price_ugx": q.unit_price_ugx, "page_rule_id": q.page_rule_id,
                    "line_total_ugx": q.line_total_ugx, "lines": list(q.lines),
                }
                for i, (s, q) in enumerate(zip(specs, self.items, strict=True))
            ],
            "order_lines": list(self.order_lines),
        }  # fmt: skip


def _page_rule(rules: Sequence[Rule], spec: ItemSpec) -> Rule:
    candidates = [
        r for r in rules
        if r.kind == "PER_PAGE" and r.paper_size == spec.paper_size and r.color_mode == spec.color_mode
        and (r.duplex is None or r.duplex == spec.duplex)
    ]  # fmt: skip
    if not candidates:
        raise PricingError(
            "unsupported_combination",
            f"This shop does not offer {spec.paper_size} {spec.color_mode}{' double-sided' if spec.duplex else ''} printing.",
        )
    # An exact duplex rule beats a generic one; ties resolve by id so the result is deterministic.
    return sorted(candidates, key=lambda r: (r.duplex is None, r.id))[0]


def _extra_rule(rules: Sequence[Rule], key: str) -> Rule:
    found = sorted(
        (r for r in rules if r.kind in ("PER_COPY", "PER_ORDER") and r.option_key == key),
        key=lambda r: r.id,
    )
    if not found:
        raise PricingError("unsupported_option", f"This shop does not offer the '{key}' option.")
    return found[0]


def quote_items(rules: Sequence[Rule], items: Sequence[ItemSpec]) -> Quote:
    if not items:
        raise PricingError("empty_order", "Add at least one document.")
    item_quotes: list[ItemQuote] = []
    order_extras: dict[str, Rule] = {}

    for spec in items:
        if spec.page_count < 1:
            raise PricingError("invalid_pages", "A document must have at least one page.")
        if not 1 <= spec.copies <= MAX_COPIES:
            raise PricingError("invalid_copies", f"Copies must be between 1 and {MAX_COPIES}.")
        page_rule = _page_rule(rules, spec)
        pages_total = spec.page_count * spec.copies
        lines: list[dict[str, Any]] = [
            {"label": "Printing", "rule_id": page_rule.id, "quantity": pages_total,
             "unit_ugx": page_rule.amount_ugx, "amount_ugx": pages_total * page_rule.amount_ugx}
        ]  # fmt: skip
        line_total = pages_total * page_rule.amount_ugx
        for key, wanted in sorted(spec.options.items()):
            if not wanted:
                continue
            extra = _extra_rule(rules, key)
            if extra.kind == "PER_COPY":
                amount = extra.amount_ugx * spec.copies
                lines.append(
                    {
                        "label": key,
                        "rule_id": extra.id,
                        "quantity": spec.copies,
                        "unit_ugx": extra.amount_ugx,
                        "amount_ugx": amount,
                    }
                )
                line_total += amount
            else:
                order_extras[key] = extra
        item_quotes.append(
            ItemQuote(
                unit_price_ugx=page_rule.amount_ugx, line_total_ugx=line_total,
                page_rule_id=page_rule.id, lines=tuple(lines),
            )
        )  # fmt: skip

    order_lines = tuple(
        {
            "label": key,
            "rule_id": r.id,
            "quantity": 1,
            "unit_ugx": r.amount_ugx,
            "amount_ugx": r.amount_ugx,
        }
        for key, r in sorted(order_extras.items())
    )
    total = sum(q.line_total_ugx for q in item_quotes) + sum(
        line["amount_ugx"] for line in order_lines
    )
    if total <= 0:
        raise PricingError("invalid_total", "The order total must be greater than zero.")
    if total > MAX_TOTAL_UGX:
        raise PricingError(
            "order_too_large", "This order is too large. Please split it into smaller orders."
        )
    return Quote(items=tuple(item_quotes), order_lines=order_lines, total_ugx=total)
