"""Fast unit tests for pure filtering/formatting logic (no network)."""
import os
import importlib

import pytest

os.environ.setdefault("BOT_TOKEN", "TEST_TOKEN")

import car_prices
import market_prices
import v13_ad_filter
import v13_media_branding


# --- ad filter -------------------------------------------------------------

@pytest.mark.parametrize("title", [
    "ارائه خدمات واسطه پرداخت ارزی",
    "از طریق سایت ما اکانت را تهیه کنید",
    "شما می‌توانید همین امروز خرید کنید",
])
def test_ad_filter_blocks_reseller_language(title):
    blocked, _ = v13_ad_filter.is_promotional_content(title)
    assert blocked


@pytest.mark.parametrize("title", [
    "ایران از طریق مذاکره به توافق رسید و بعدها درباره خرید نفت صحبت شد",
    "قیمت نفت امروز افزایش یافت",
    "زلزله ۶ ریشتری در ترکیه",
])
def test_ad_filter_keeps_ordinary_news(title):
    blocked, reason = v13_ad_filter.is_promotional_content(title)
    assert not blocked, reason


# --- car prices ------------------------------------------------------------

def _found(*models):
    return {m: {"model": m, "year": "1404", "market": "1,000"} for m in models}


def test_car_base_model_does_not_take_variant_price():
    found = _found("شاهین اتوماتیک", "شاهین G")
    assert car_prices.choose_model(found, ("شاهین",))["model"] == "شاهین G"
    assert car_prices.choose_model(found, ("شاهین اتوماتیک",))["model"] == "شاهین اتوماتیک"


def test_car_board_respects_telegram_limit():
    found = _found("پژو 207", "دنا پلاس", "شاهین G")
    found["پژو 207"]["market"] = "9" * 5000
    text, count = car_prices.build_board("۱۰ مهر ۱۴۰۵", found)
    assert len(text) <= car_prices.MAX_MESSAGE_CHARS
    assert count == 2


def test_car_block_has_no_literal_markdown():
    block = car_prices.format_price_block("پژو ۲۰۷", {"market": "1"})
    assert "**" not in block


# --- market prices ---------------------------------------------------------

def test_market_numeric_check():
    rows = {"USD": ["دلار", "USD", "۸۵,۰۰۰"], "EUR": ["یورو", "EUR", "-"]}
    assert market_prices.has_numeric_value(rows, "USD")
    assert not market_prices.has_numeric_value(rows, "EUR")
    assert not market_prices.has_numeric_value(rows, "GBP")


# --- media branding --------------------------------------------------------

def test_caption_sanitizer_removes_urls_and_source_line():
    text = "سلام https://example.com/a   دنیا\nمنبع: ایرنا"
    assert v13_media_branding._sanitize_caption_text(text) == "سلام دنیا"


def test_caption_sanitizer_keeps_line_breaks():
    assert "\n" in v13_media_branding._sanitize_caption_text("خط اول\nخط دوم")


# --- editorial word boundaries --------------------------------------------

def test_short_latin_tokens_are_word_bounded():
    try:
        patch = importlib.import_module("v13_editorial_final_patch")
    except Exception as exc:  # heavy engine import unavailable locally
        pytest.skip(f"engine import unavailable: {exc}")
    assert not patch._title_is_major_global_event("Business leaders said review is due")
    assert patch._title_is_major_global_event("US strikes militia sites")
    assert patch._title_is_major_global_event("OpenAI launches new model")


# --- editorial formatter ---------------------------------------------------

def test_incomplete_check_uses_whole_final_word():
    import v13_editorial_formatter as fmt
    assert fmt._is_incomplete("داروی جدید عرضه شد و")
    assert fmt._is_incomplete("وزیر گفت که")
    assert not fmt._is_incomplete("بیمار به دارو")
    assert not fmt._is_incomplete("خبر کامل است.")
