FROM python:3.12.4-slim-bookworm

WORKDIR /usr/src/app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONBUFFERED 1

#RUN apt-get update && apt-get install -y netcat-traditional
#RUN pip install --upgrade pip

COPY ./requirements.txt /usr/src/app/requirements.txt
RUN pip install -r requirements.txt

COPY . /usr/src/app

#CMD ["python", "./app.py"]
#ENTRYPOINT ["/usr/src/app/entrypoint.sh"]