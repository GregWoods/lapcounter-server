
# Setting up the lapcounter web server on the Raspberry Pi


based loosely on these: 
https://www.digitalocean.com/community/tutorials/how-to-install-nginx-on-ubuntu-18-04

https://www.digitalocean.com/community/tutorials/how-to-serve-flask-applications-with-gunicorn-and-nginx-on-ubuntu-18-04

But without using a venv

Assumes the basics of a **raspberry pi desktop OS** installation have already been done

```
cd ~
mkdir lapcounter
cd lapcounter
mkdir backend
cd backend

sudo apt update
sudo apt install python3-pip python3-dev build-essential libssl-dev libffi-dev python3-setuptools ufw nginx

## setup the firewall

```
sudo ufw enable
sudo ufw allow 'SSH'
sudo ufw allow 'Nginx HTTP'

--some like this line will be needed to open a port for websockets
sudo ufw allow 8080/tcp

sudo ufw status
```


pip install wheel
pip install gunicorn flask




nano test.py
```

contains...

```
from flask import Flask
app = Flask(__name__)

@app.route("/")
def hello():
    return "<h1 style='color:blue'>Hello There!</h1>"

if __name__ == "__main__":
    app.run(host='0.0.0.0')
```

Temporary hole in firewall

```sudo ufw allow 5000```

Test it 

```gunicorn --bind 0.0.0.0:5000 wsgi:app```

## Make it launch on startup


```sudo nano /etc/systemd/system/lapcounter.service```

```
[Unit]
Description=Gunicorn instance to serve lapcounter web server
After=network.target

[Service]
User=pi
Group=www-data
WorkingDirectory=/home/pi/lapcounter/backend
Environment="PATH=/home/pi/lapcounter/backend/bin"
ExecStart=/usr/bin/gunicorn --workers 3 wsgi:app --bind=unix:/home/pi/lapcounter/backend/lapcounter.sock

[Install]
WantedBy=multi-user.target
```

```systemctl start lapcounter```

```sudo nano /etc/nginx/sites-available/lapcounter```

contains

```
server {
    listen 80;
    server_name localhost;

    location / {
        include proxy_params;
        proxy_pass http://unix:/home/pi/lapcounter/lapcounter.sock;
    }
}
```


sudo ln -s /etc/nginx/sites-available/lapcounter /etc/nginx/sites-enabled

test syntax

sudo nginx -t


sudo systemctl restart nginx