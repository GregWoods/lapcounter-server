from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # API_URL/REACT_URL are no longer used: CORS accepts any origin and car image URLs come
    # from the request. Kept optional so existing compose files and .env files still load.
    API_URL: str = ""
    REACT_URL: str = ""
    MEDIA_FOLDER: str
    CARS_MEDIA_FOLDER: str
    DB_DATABASE: str
    DB_HOST: str
    DB_USER: str
    DB_PASSWORD: str
    DB_PORT: int
    # The broker the race_state subscriber reads (#79).
    MQTT_HOSTNAME: str = "mosquitto"
    MQTT_PORT: int = 1883
    model_config = SettingsConfigDict(env_file=".env")