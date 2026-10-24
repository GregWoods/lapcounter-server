import pytest

from app_settings import AppSettingsUpdate, validate_update


def test_only_sent_fields_are_returned():
    assert validate_update(AppSettingsUpdate(wifi_ssid="Track")) == {"wifi_ssid": "Track"}


def test_empty_string_is_a_real_value():
    # Clearing the password must be possible, so "" is kept (only None means "not sent").
    assert validate_update(AppSettingsUpdate(wifi_password="")) == {"wifi_password": ""}


def test_bad_security_rejected():
    with pytest.raises(ValueError):
        validate_update(AppSettingsUpdate(wifi_security="WPA3-ish"))


def test_base_url_normalised():
    out = validate_update(AppSettingsUpdate(public_base_url=" http://10.0.0.5:8088/ "))
    assert out == {"public_base_url": "http://10.0.0.5:8088"}


def test_base_url_needs_scheme():
    with pytest.raises(ValueError):
        validate_update(AppSettingsUpdate(public_base_url="10.0.0.5"))


def test_too_long_rejected():
    with pytest.raises(ValueError):
        validate_update(AppSettingsUpdate(wifi_ssid="x" * 256))
