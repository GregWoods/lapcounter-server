"""Installation-wide settings (the app_settings table): WiFi details for the Welcome page
QR code and an optional public base URL. DB-free validation lives here so it is testable."""

from typing import Optional

from pydantic import BaseModel

WIFI_SECURITY_VALUES = ("WPA", "WEP", "nopass")

DEFAULTS = {
    "wifi_ssid": "",
    "wifi_password": "",
    "wifi_security": "WPA",
    "public_base_url": "",
}


class AppSettingsUpdate(BaseModel):
    """Partial update: only the fields sent are changed."""
    wifi_ssid: Optional[str] = None
    wifi_password: Optional[str] = None
    wifi_security: Optional[str] = None
    public_base_url: Optional[str] = None


def validate_update(update: AppSettingsUpdate) -> dict:
    """Return the {key: value} pairs to store, or raise ValueError describing the problem."""
    changes = {k: v for k, v in update.model_dump().items() if v is not None}
    if "wifi_security" in changes and changes["wifi_security"] not in WIFI_SECURITY_VALUES:
        raise ValueError(f"wifi_security must be one of {', '.join(WIFI_SECURITY_VALUES)}")
    if "public_base_url" in changes:
        url = changes["public_base_url"].strip().rstrip("/")
        if url and not url.lower().startswith(("http://", "https://")):
            raise ValueError("public_base_url must start with http:// or https://")
        changes["public_base_url"] = url
    for key, value in changes.items():
        if len(value) > 255:
            raise ValueError(f"{key} is too long (max 255 characters)")
    return changes
