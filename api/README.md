# Standalone Scalextric Digital Lap Counter - Python API

## Powershell over Ubuntu

I have set up the new python virtual env in Powershell, because I am also running the build-and-push
scripts in Powershell. Mixing Powershell and Ubuntu causes permissions errors.
Note that Ubuntu would have been fine... just stick to one!

## Use pyenv!

It is installed globalled, and allows changing python version
 ```
pyenv versions
pyenv install --list
pyenv install 3.12.2
 ```

## Running with Docker


From the ```api``` folder, we need to specify the compose file in the parent folder
```
docker compose -f ../compose.yaml up --build --detach api
```


### Endpoints (see __init__.py)

These endpoints all work in Docker... but not when running locally
```
http://127.0.0.1:5001
http://127.0.0.1:5001/upload
http://127.0.0.1:5001/media/01595327e5339118540a72a10b7c61521e3eafb74b.jpg
```


 ## Running without Docker

Not recomended. Docker saves installing a lot of stuff on your development PC, and 
keeps your dev environment the same as the production environment on the 
Raspberry Pi

```
./venv/Scripts/activate
pip install -r requirements.txt
./setenv.ps1
python manage.py run
```