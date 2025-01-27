import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    http_protocol: str
    server_ip_addr: str
    api_port: str
    react_port: str
    media_folder: str = "media/cars"

    @property
    def api_base_url(self) -> str:
        return f"{self.http_protocol}://{self.server_ip_addr}:{self.api_port}"
    
    @property
    def api_react_url(self) -> str:
        return f"{self.http_protocol}://{self.server_ip_addr}:{self.react_port}"


settings = Settings()

app = FastAPI()
app.mount("/media", StaticFiles(directory="media"), name="media")

cors_origins = [
    settings.api_react_url 
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/settings")
async def info():
    return settings.api_react_url


@app.get("/api/cars")
def get_cars():
    folder_path = os.path.join(settings.media_folder)
    print(f"Folder path: {folder_path}")
    api_base_url = settings.api_base_url
    print(f"API base URL: {api_base_url}")
    print(f"CORS origins: {cors_origins}")
    print(os.listdir(folder_path))

    files = [f"{api_base_url}/media/cars/{filename}" for filename in os.listdir(folder_path)]
    return files
