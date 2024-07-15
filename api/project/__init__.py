import os

from flask import (
    Flask,
    jsonify,
    send_from_directory,
    request,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import os
from flask_cors import CORS


app = Flask(__name__)
CORS(app)  # This will enable CORS for all routes
app.config.from_object("project.config.Config")
db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(128), unique=True, nullable=False)
    active = db.Column(db.Boolean(), default=True, nullable=False)

    def __init__(self, email):
        self.email = email


@app.route("/")
def hello_world():
    return jsonify(hello="world")


@app.route("/media/<path:filename>")
def mediafiles(filename):
    return send_from_directory(app.config["MEDIA_FOLDER"], filename)


@app.route("/upload", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        file = request.files["file"]
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config["MEDIA_FOLDER"], "cars", filename))
    return """
    <!doctype html>
    <title>upload new File</title>
    <form action="" method=post enctype=multipart/form-data>
      <p><input type=file name=file><input type=submit value=Upload>
    </form>
    """

@app.route("/api/cars", methods=["GET"])
def get_cars():
    folder_path = os.path.join(app.config["MEDIA_FOLDER"], "cars")
    api_base_url = os.environ.get("API_BASE_URL", "http://127.0.0.1:5001")
    files = [f"{api_base_url}/media/cars/{filename}" for filename in os.listdir(folder_path)]
    return jsonify(files)