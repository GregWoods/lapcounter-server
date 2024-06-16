from flask import Flask, jsonify
from os import listdir, path
import json


app = Flask(__name__)
print("app.root_path: ", app.root_path)
#app.root_path:  C:\Users\gregw\scalextric\scalextric-lapcounter-react\backend

print("app.instance_path: ", app.instance_path)
#app.instance_path:  C:\Users\gregw\scalextric\scalextric-lapcounter-react\backend\instance 

print(path.join(app.root_path, "..", "public", "images", "cars"))


@app.route("/")
def hello():
    return "<h1 style='color:blue'>Hello There!</h1>"


@app.route("/api/cars")
def list_car_images():
    rootpath = path.dirname(app.root_path)   #go up one folder from the current "backend" folder
    mypath = path.join(rootpath, "public", "images", "cars")
    onlyfiles = [f for f in listdir(mypath) if path.isfile(path.join(mypath, f))]
    response = jsonify(onlyfiles)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


if __name__ == "__main__":
    app.run(host='0.0.0.0')
