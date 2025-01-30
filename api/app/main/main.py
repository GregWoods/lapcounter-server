import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_URL: str
    REACT_URL: str
    MEDIA_FOLDER: str
    CARS_MEDIA_FOLDER: str


settings = Settings()

app = FastAPI()
app.mount("/media", StaticFiles(directory="media"), name="media")

cors_origins = [
    settings.REACT_URL 
]

print(f"CORS origins: {cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/settings")
async def info():
    return settings.REACT_URL


@app.get("/api/cars")
def get_cars():
    folder_path = os.path.join(settings.CARS_MEDIA_FOLDER)
    print(f"Folder path: {folder_path}")
    api_base_url = settings.API_URL
    print(f"API base URL: {api_base_url}")
    print(f"CORS origins: {cors_origins}")
    print(os.listdir(folder_path))

    files = [f"{api_base_url}/{settings.CARS_MEDIA_FOLDER}/{filename}" for filename in os.listdir(folder_path)]
    return files
