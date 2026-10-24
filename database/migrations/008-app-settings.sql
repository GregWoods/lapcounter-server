-- 008: app_settings — global key/value settings that belong to the installation rather than
-- to any one meeting (WiFi SSID/password/security for the Welcome page QR code, and an
-- optional public base URL for the meeting QR code). See GitHub issue #71.
--
-- Re-running is safe. The API also creates the table at startup (create_all), so this is
-- for an explicit upgrade.
--
-- Apply:
--   docker exec -i database psql -U lap -d lapcounter_server < database/migrations/008-app-settings.sql

CREATE TABLE IF NOT EXISTS app_settings (
    key VARCHAR(64) PRIMARY KEY,
    value VARCHAR(255) NOT NULL
);
