from decimal import Decimal
import pytest

from app.services.premium import (
    PremiumLine,
    PremiumQuote,
    calculate_premium,
)


def test_refrigerator_basic_age_one_standard_calculation():
    quote = calculate_premium("REFRIGERATION", Decimal("100000.00"), 1, "BASIC")
    assert isinstance(quote, PremiumQuote)
    assert quote.category == "REFRIGERATION"
    assert quote.cover == "BASIC"
    assert quote.total == Decimal("2000.00")

    base_line = quote.lines[0]
    assert base_line.label == "Base premium"
    assert base_line.amount == Decimal("2000.00")

    age_line = quote.lines[1]
    assert age_line.label == "Age charge"
    assert age_line.amount == Decimal("0.00")

    cover_line = quote.lines[2]
    assert cover_line.label == "Cover charge"
    assert cover_line.amount == Decimal("0.00")

    min_line = quote.lines[3]
    assert min_line.label == "Minimum premium adjustment"
    assert min_line.amount == Decimal("0.00")


def test_age_four_raises_age_charge_by_ten_percent_of_base():
    quote = calculate_premium("REFRIGERATION", Decimal("100000.00"), 4, "BASIC")
    base_line = quote.lines[0]
    age_line = quote.lines[1]
    assert base_line.amount == Decimal("2000.00")
    assert age_line.amount == Decimal("200.00")
    assert age_line.amount == base_line.amount * Decimal("0.10")
    assert quote.total == Decimal("2200.00")


def test_comprehensive_adds_forty_percent_of_base_as_cover_charge():
    quote = calculate_premium("REFRIGERATION", Decimal("100000.00"), 1, "COMPREHENSIVE")
    base_line = quote.lines[0]
    cover_line = quote.lines[2]
    assert base_line.amount == Decimal("2000.00")
    assert cover_line.amount == Decimal("800.00")
    assert cover_line.amount == base_line.amount * Decimal("0.40")
    assert quote.total == Decimal("2800.00")


def test_small_sum_insured_hits_minimum_premium():
    quote = calculate_premium("REFRIGERATION", Decimal("1000.00"), 1, "BASIC")
    assert quote.total == Decimal("500.00")
    base_line = quote.lines[0]
    min_line = quote.lines[3]
    assert base_line.amount == Decimal("20.00")
    assert min_line.label == "Minimum premium adjustment"
    assert min_line.amount == Decimal("480.00")
    assert min_line.amount > Decimal("0.00")


@pytest.mark.parametrize(
    "category,sum_insured,age_years,cover",
    [
        ("COOKING", Decimal("25000.00"), 3, "STANDARD"),
        ("HVAC", Decimal("4500.00"), 8, "BASIC"),
        ("ELECTRICAL", Decimal("350000.00"), 6, "COMPREHENSIVE"),
    ],
)
def test_sum_of_lines_equals_total_for_various_inputs(
    category, sum_insured, age_years, cover
):
    quote = calculate_premium(category, sum_insured, age_years, cover)
    lines_sum = sum(line.amount for line in quote.lines)
    assert lines_sum == quote.total


def test_unknown_category_raises_value_error():
    with pytest.raises(ValueError, match="Unknown equipment category"):
        calculate_premium("SPACESHIP", Decimal("10000.00"), 1, "BASIC")

    with pytest.raises(ValueError, match="Unknown cover level"):
        calculate_premium("REFRIGERATION", Decimal("10000.00"), 1, "ULTRA")


def test_zero_or_negative_sum_insured_raises_value_error():
    with pytest.raises(ValueError, match="Sum insured must be greater than zero"):
        calculate_premium("REFRIGERATION", Decimal("0.00"), 1, "BASIC")

    with pytest.raises(ValueError, match="Sum insured must be greater than zero"):
        calculate_premium("REFRIGERATION", Decimal("-500.00"), 1, "BASIC")


def test_negative_age_raises_value_error():
    with pytest.raises(ValueError, match="Age in years cannot be negative"):
        calculate_premium("REFRIGERATION", Decimal("10000.00"), -1, "BASIC")

