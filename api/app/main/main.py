import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Lapcounter Server API"
    admin_email: str = "gregwoodslancs@gmail.com"
    media_folder: str = "media/cars"
    api_base_url: str = "http://127.0.0.1:8000"
    #SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite://")
    #SQLALCHEMY_TRACK_MODIFICATIONS = False
    #STATIC_FOLDER = f"{os.getenv('APP_FOLDER')}/project/static"
    #MEDIA_FOLDER = f"{os.getenv('APP_FOLDER')}/project/media"

settings = Settings()
app = FastAPI()
app.mount("/media", StaticFiles(directory="media"), name="media")

origins = [
    "http://localhost:8088",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/info")
async def info():
    return {
        "app_name": settings.app_name,
        "admin_email": settings.admin_email,
        "media_folder": settings.media_folder,
    }


@app.get("/api/cars")
def get_cars():
    folder_path = os.path.join(settings.media_folder)
    print(f"Folder path: {folder_path}")
    api_base_url = settings.api_base_url
    print(f"API base URL: {api_base_url}")
    print(os.listdir(folder_path))

    files = [f"{api_base_url}/media/cars/{filename}" for filename in os.listdir(folder_path)]
    return files
