import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    vite_http_protocol: str
    vite_server_ip_addr: str
    vite_api_port: str
    react_port: str
    react_cors_origin: str
    vite_mqtt_protocol: str
    vite_mqtt_hostname: str
    vite_mqtt_port: str
    vite_media_folder: str

    @property
    def api_base_url(self) -> str:
        return f"{self.vite_http_protocol}://{self.vite_server_ip_addr}:{self.vite_api_port}"
    
    @property
    def api_react_url(self) -> str:
        return f"{self.vite_http_protocol}://{self.vite_server_ip_addr}:{self.react_port}"


settings = Settings()

app = FastAPI()
app.mount("/media", StaticFiles(directory="media"), name="media")

cors_origins = [
    settings.react_cors_origin 
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
    return settings.api_react_url


@app.get("/api/cars")
def get_cars():
    folder_path = os.path.join(settings.vite_media_folder)
    print(f"Folder path: {folder_path}")
    api_base_url = settings.api_base_url
    print(f"API base URL: {api_base_url}")
    print(f"CORS origins: {cors_origins}")
    print(os.listdir(folder_path))

    files = [f"{api_base_url}/{settings.vite_media_folder}/{filename}" for filename in os.listdir(folder_path)]
    return files
