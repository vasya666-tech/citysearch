from flask import Flask, render_template, request, jsonify, make_response, redirect, url_for
from sqlalchemy import create_engine, Table, Column, Integer, String, MetaData, select
from os import getenv
from dotenv import load_dotenv
import psycopg2
from requests import get
from datetime import datetime, timedelta, timezone
import hashlib
import jwt

load_dotenv()
DB = getenv('DB_URL')
KEY = getenv('KEY')

engine = create_engine(DB)
connection = engine.connect()

metadata = MetaData()
city = Table(
    "city",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String),
    Column("population", Integer),
    Column("description", String),
    Column("image", String)
    )

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String),
    Column("password_hash", String)
    )
 
app = Flask(__name__)

@app.errorhandler(404) 
def not_found(e):
    return render_template('error.html')

@app.get('/')
def main():
    token = request.cookies.get("token")
    if token:
        return redirect(url_for("profile_page"))
    return render_template('index.html')

@app.get('/login')
def login_page():
    token = request.cookies.get("token")
    if token:
        return redirect(url_for('profile_page'))
    return render_template('login.html')

@app.post('/reg')
def reg():
    data = request.get_json()
    username = data.get("user")
    password = data.get("passw")
    if len(password) < 4:
        return jsonify({"error": "The password must contain at least 4 characters!"})
    h = hashlib.sha512(password.encode()).hexdigest()
    id_bd = connection.execute(select(users.c.id).where(users.c.username == username)).fetchone()
    if not id_bd:
        result = connection.execute(users.insert().values(username=username, password_hash=h))
        connection.commit()
        
        user_id = result.inserted_primary_key[0]
        payload = {
            "user_id": user_id,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1)
            }
        token = jwt.encode(payload, KEY, algorithm="HS256")
        
        response = jsonify({"message": "user registered"})
        response.set_cookie("token", token)
        return response
    return jsonify({"owned": True})

@app.post('/login')
def login():
    data = request.get_json()
    username = data.get("user")
    password = data.get("passw")
    if len(password) < 4:
        return jsonify({"error": "The password must contain at least 4 characters!"})
    h = hashlib.sha512(password.encode()).hexdigest()
    user = connection.execute(select(users.c.id, users.c.password_hash).where(users.c.username == username)).first()
    if user is None:
        return jsonify({"error": "User is not found."})
    if h == user.password_hash:
        payload = {
            "user_id": user.id,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1)
            }
        token = jwt.encode(payload, KEY, algorithm="HS256")
        response = jsonify({"message": "user registered"})
        response.set_cookie("token", token)
        return response
    return jsonify({"error": "The password is incorrect"})

@app.get("/profile")
def profile_page():
    token = request.cookies.get("token")
    if not token:
        return redirect(url_for('main')) 
    try:
        data = jwt.decode(token, KEY, algorithms="HS256")
        user_id = data["user_id"]
        username = connection.execute(select(users.c.username).where(users.c.id == user_id)).first()
        return render_template("index.html", username=username[0], logout=True)

    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Срок действия токена истек"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Недействительный токен"}), 401

@app.get("/logout")
def logout():
    response = make_response(redirect(url_for("main")))
    response.set_cookie("token", " ", max_age=0, expires=0, path="/")
    return response

@app.post('/trade')
def trade():
    data = request.get_json()
    city_name = data.get("message")
    if city_name:
        city_name = city_name.title()
    geo = get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={
            "name": city_name,
            "count": 1,
            "language": "en"
        }
    ).json()
    latitude = geo["results"][0]["latitude"]
    longitude = geo["results"][0]["longitude"]
    weather_response = get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m"
        },
        headers={
            "User-Agent": "MyWeatherApp/1.0"
        },
        timeout=10
        )
    if weather_response.status_code == 429:
        temperature = "N/A"
    else:
        weather_response.raise_for_status()
        weather = weather_response.json()
        temperature = f"{weather['current']['temperature_2m']}°C"
    population = connection.execute(select(city.c.population).where(city.c.name == city_name)).scalar()
    description = connection.execute(select(city.c.description).where(city.c.name == city_name)).scalar()
    image = connection.execute(select(city.c.image).where(city.c.name == city_name)).scalar()
    
    if population is not None and description is not None:
        return jsonify({
            "name": city_name,
            "population": population,
            "description": description,
            "image": image,
            "temperature": temperature
            }
                       )
    return jsonify({"error": "Try another city, please."}), 404
