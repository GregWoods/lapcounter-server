from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    API_URL: str
    REACT_URL: str
    MEDIA_FOLDER: str
    CARS_MEDIA_FOLDER: str
    DB_DATABASE: str
    DB_HOST: str
    DB_USER: str
    DB_PASSWORD: str
    DB_PORT: int
    model_config = SettingsConfigDict(env_file=".env")