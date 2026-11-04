from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import enum
from typing import Any

from app.models.enums import EquipmentCategory


class CoverLevel(str, enum.Enum):
    BASIC = "BASIC"
    STANDARD = "STANDARD"
    COMPREHENSIVE = "COMPREHENSIVE"


CATEGORY_RATE: dict[EquipmentCategory, Decimal] = {
    EquipmentCategory.REFRIGERATION: Decimal("0.020"),
    EquipmentCategory.COOKING: Decimal("0.018"),
    EquipmentCategory.MACHINERY: Decimal("0.025"),
    EquipmentCategory.HVAC: Decimal("0.015"),
    EquipmentCategory.ELECTRICAL: Decimal("0.022"),
    EquipmentCategory.OTHER: Decimal("0.030"),
}

COVER_CHARGE_PCT: dict[CoverLevel, Decimal] = {
    CoverLevel.BASIC: Decimal("0.00"),
    CoverLevel.STANDARD: Decimal("0.20"),
    CoverLevel.COMPREHENSIVE: Decimal("0.40"),
}

MINIMUM_PREMIUM = Decimal("500.00")
TWOPLACES = Decimal("0.01")


def get_age_charge_pct(age_years: int) -> Decimal:
    if age_years <= 2:
        return Decimal("0.00")
    elif age_years <= 5:
        return Decimal("0.10")
    else:
        return Decimal("0.25")


@dataclass(frozen=True)
class PremiumLine:
    label: str
    amount: Decimal


@dataclass(frozen=True)
class PremiumQuote:
    category: str
    sum_insured: Decimal
    age_years: int
    cover: str
    lines: tuple[PremiumLine, ...]
    total: Decimal


def _normalize_rates(rates: Any) -> dict[tuple[str, str], Decimal]:
    lookup: dict[tuple[str, str], Decimal] = {}
    if rates is None:
        return lookup

    if isinstance(rates, dict):
        for k, v in rates.items():
            if isinstance(k, tuple) and len(k) == 2:
                lookup[(str(k[0]).upper(), str(k[1]).upper())] = Decimal(str(v))
            elif isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    lookup[(str(k).upper(), str(sub_k).upper())] = Decimal(str(sub_v))
            else:
                str_k = str(k).upper()
                if ":" in str_k:
                    parts = str_k.split(":", 1)
                    lookup[(parts[0], parts[1])] = Decimal(str(v))
                elif str_k in {"MINIMUM", "MINIMUM_PREMIUM"}:
                    lookup[("MINIMUM", "MINIMUM_PREMIUM")] = Decimal(str(v))
    elif isinstance(rates, (list, tuple)):
        for item in rates:
            if isinstance(item, dict):
                kind = str(item.get("kind", "")).upper()
                code = str(item.get("code", "")).upper()
                val = item.get("value")
                if kind and code and val is not None:
                    lookup[(kind, code)] = Decimal(str(val))
            elif hasattr(item, "kind") and hasattr(item, "code") and hasattr(item, "value"):
                lookup[(str(item.kind).upper(), str(item.code).upper())] = Decimal(str(item.value))

    return lookup


def _lookup_rate(
    lookup: dict[tuple[str, str], Decimal],
    kind: str,
    codes: tuple[str, ...],
    default: Decimal,
) -> Decimal:
    for code in codes:
        val = lookup.get((kind.upper(), code.upper()))
        if val is not None:
            return val
    return default


def calculate_premium(
    category: str | EquipmentCategory,
    sum_insured: Decimal,
    age_years: int,
    cover: str | CoverLevel,
    rates: dict | None = None,
) -> PremiumQuote:
    try:
        if isinstance(category, EquipmentCategory):
            cat = category
        elif isinstance(category, str):
            cat = EquipmentCategory(category.strip().upper())
        else:
            raise ValueError(f"Unknown equipment category: {category!r}")
    except (ValueError, KeyError, AttributeError):
        raise ValueError(f"Unknown equipment category: {category!r}")

    try:
        if isinstance(cover, CoverLevel):
            cov = cover
        elif isinstance(cover, str):
            cov = CoverLevel(cover.strip().upper())
        else:
            raise ValueError(f"Unknown cover level: {cover!r}")
    except (ValueError, KeyError, AttributeError):
        raise ValueError(f"Unknown cover level: {cover!r}")

    if not isinstance(sum_insured, Decimal):
        try:
            sum_insured = Decimal(str(sum_insured))
        except Exception:
            raise ValueError("sum_insured must be a valid positive Decimal")

    if sum_insured <= Decimal("0"):
        raise ValueError("Sum insured must be greater than zero")

    if not isinstance(age_years, int) or isinstance(age_years, bool):
        raise ValueError("Age in years must be a non-negative integer")

    if age_years < 0:
        raise ValueError("Age in years cannot be negative")

    rate_lookup = _normalize_rates(rates)
    cat_rate = _lookup_rate(rate_lookup, "CATEGORY", (cat.value,), CATEGORY_RATE[cat])

    if age_years <= 2:
        age_charge_pct = _lookup_rate(
            rate_lookup, "AGE_BAND", ("0_2", "0-2", "0_TO_2"), get_age_charge_pct(age_years)
        )
    elif age_years <= 5:
        age_charge_pct = _lookup_rate(
            rate_lookup, "AGE_BAND", ("3_5", "3-5", "3_TO_5"), get_age_charge_pct(age_years)
        )
    else:
        age_charge_pct = _lookup_rate(
            rate_lookup, "AGE_BAND", ("6_PLUS", "6+", "6_OR_MORE"), get_age_charge_pct(age_years)
        )

    cov_charge_pct = _lookup_rate(rate_lookup, "COVER", (cov.value,), COVER_CHARGE_PCT[cov])
    min_premium = _lookup_rate(
        rate_lookup, "MINIMUM", ("MINIMUM_PREMIUM", "DEFAULT", "MINIMUM"), MINIMUM_PREMIUM
    )

    base = (sum_insured * cat_rate).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    age_charge = (base * age_charge_pct).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    cover_charge = (base * cov_charge_pct).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    subtotal = base + age_charge + cover_charge
    total = max(subtotal, min_premium).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    min_adjustment = (total - subtotal).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    lines = (
        PremiumLine("Base premium", base),
        PremiumLine("Age charge", age_charge),
        PremiumLine("Cover charge", cover_charge),
        PremiumLine("Minimum premium adjustment", min_adjustment),
    )

    return PremiumQuote(
        category=cat.value,
        sum_insured=sum_insured,
        age_years=age_years,
        cover=cov.value,
        lines=lines,
        total=total,
    )
