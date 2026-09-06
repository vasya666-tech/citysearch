from flask import Flask, render_template, request, jsonify, make_response, redirect, url_for
from sqlalchemy import create_engine, Table, Column, Integer, String, MetaData, select, update, delete
from os import getenv
from dotenv import load_dotenv
import psycopg2
from requests import get
from datetime import datetime, timedelta, timezone
import hashlib
import jwt
from time import time
import smtplib
from secrets import randbelow

load_dotenv()
DB = getenv('DB_URL')
KEY = getenv('KEY')
ID = getenv('CLIENT_ID')
SECRET = getenv('CLIENT_SECRET')
GMAIL = getenv('GMAIL')
APP_PSWD = getenv('APP_PSWD')

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
    Column("password_hash", String),
    Column("flights", String),
    Column('email', String)
    )
 
app = Flask(__name__)

@app.errorhandler(404) 
def not_found(e):
    return render_template('base.html', error=True)

@app.get('/cookies')
def cookies():
    return  render_template('base.html', cookies=True)

@app.get('/')
def main():
    if request.cookies.get("token"):
        return redirect(url_for("profile_page"))
    return render_template('index.html')

@app.get('/login')
def login_page():
    return render_template('login.html')

codes = {}
users_block = {
    'emails': {},
    'ips': {}}

@app.post('/reg')
def reg():
    data = request.get_json()
    email = data.get("user")
    password = data.get("passw")
    if len(password) < 4:
        return jsonify({"error": "The password must contain at least 4 characters!"})
    id_bd = connection.execute(select(users.c.id).where(users.c.email == email)).fetchone()
    if id_bd:
        return jsonify({"owned": True})
    if email in users_block['emails'] and time() - users_block['emails'][email] < 1200:
        print('email closed')
        return jsonify({'error': 'You can get a new code only after 20 minutes.'})
    user_ip = request.remote_addr
    if user_ip in users_block['ips'] and time() - users_block['ips'][user_ip] < 1200:
        print('ip blocked')
        return jsonify({'error': 'You can get a new code only after 20 minutes.'})
    code = f"{randbelow(1000000):06d}"
    codes[email] = {
        'code': code,
        'time': time()}
    msg = f'''Subject: Verification code
From: {GMAIL}
To: {email}

Your code is: {code}
'''
    print(msg)
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(GMAIL, APP_PSWD) 
        server.sendmail(GMAIL, email, msg)
    users_block['ips'][user_ip] = users_block['emails'][email] = time()
    print(users_block)
    return jsonify({'message': 'code_sent'})

@app.post('/confirm')
def reg_confirm():
    data = request.get_json()
    email = data.get("user")
    code = data.get("code")
    password = data.get("passw")
    username = data.get('username')
    if time() - codes[email]['time'] < 90:
        if codes[email]['code'] == code:
            h = hashlib.sha512(password.encode()).hexdigest()
            result = connection.execute(users.insert().values(username=username, email=email, password_hash=h))
            connection.commit()

            user_id = result.inserted_primary_key[0]
            payload = {
                "user_id": user_id,
                "exp": datetime.now(timezone.utc) + timedelta(hours=1)
                }
            token = jwt.encode(payload, KEY, algorithm="HS256")
            
            response = jsonify({"message": "registered"})
            response.set_cookie("token", token)
            print(codes)
            return response
        return jsonify({'error': 'The code is incorrect'})
    return jsonify({'error': 'The code has expired.'})

@app.post('/login')
def login():
    data = request.get_json()
    email = data.get("user")
    password = data.get("passw")
    if len(password) < 4:
        return jsonify({"error": "The password must contain at least 4 characters!"})
    user = connection.execute(select(users.c.id, users.c.password_hash).where(users.c.email == email)).first()
    if user is None:
        return jsonify({"error": 'User is not found.'})
    h = hashlib.sha512(password.encode()).hexdigest()
    if h == user.password_hash:
        payload = {
            "user_id": user.id,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1)
            }
        token = jwt.encode(payload, KEY, algorithm="HS256")
        response = jsonify({"message": "logged in"})
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
        user_data = connection.execute(select(
            users.c.username,
            users.c.flights).where(users.c.id == user_id)).mappings().first()
        return render_template("index.html",
                               username=user_data["username"],
                               flights=f'Already visited: {user_data["flights"].strip(",")}',
                               logout=True, button=True)
    except jwt.ExpiredSignatureError:
        response = make_response(redirect(url_for("login")))
        response.delete_cookie("token")
        return response
    except jwt.InvalidTokenError:
        response = make_response(redirect(url_for("main")))
        response.delete_cookie("token")
        return response

@app.get("/logout")
def logout():
    response = make_response(redirect(url_for("main")))
    response.set_cookie("token", " ", max_age=0, expires=0, path="/")
    return response

@app.post('/save')
def save():
    token = request.cookies.get("token")
    try:
        data = jwt.decode(token, KEY, algorithms="HS256")
        user_id = data["user_id"]
        flights_db = connection.execute(select(users.c.flights).where(users.c.id==user_id)).scalar()
    except jwt.ExpiredSignatureError:
        response = make_response(redirect(url_for("login")))
        response.delete_cookie("token")
        return response
    except jwt.InvalidTokenError:
        response = make_response(redirect(url_for("main")))
        response.delete_cookie("token")
        return response
    
    data = request.get_json()
    city_name = data.get("message").strip().title()
    city_name_db = connection.execute(select(city.c.name).where(city.c.name==city_name)).scalar()
    if city_name_db == city_name:
        travel_list = f"{flights_db}"
        if city_name_db not in flights_db.split(', |'):
            travel_list = f"{flights_db}{city_name_db}, |"
            set_flights = connection.execute(update(users).where(users.c.id==user_id).values(flights=travel_list))
            connection.commit()
            return jsonify({
                "message": f"You just added {city_name_db} to your travel list.",
                "travel_list": f'Already visited: {travel_list.strip(",")}'})
        return jsonify({"travel_list": f'Already visited: {travel_list.strip(",")}  ({city_name_db} is already here.)'})
    return jsonify({"message": f"City not found."})

def temperature_api(cache, city, latitude=False, longitude=False, time_passed=False):
    if latitude is False:
        geo = get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={
            "name": city,
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
            temperature = weather['current']['temperature_2m']
        
        cache[city] = {}
        cache[city]['latitude'] = latitude
        cache[city]['longitude'] = longitude
        
        cache[city]['temporal'] = {}
        cache[city]['temporal']['temperature'] = temperature
        cache[city]['temporal']['cache_time'] = time()
        print('geo, weather apis')
        return temperature

    elif latitude and longitude and time_passed:
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
            temperature = weather['current']['temperature_2m']
        
        cache[city]['temporal']['temperature'] = temperature
        cache[city]['temporal']['cache_time'] = time()
        print('weather api')
        return temperature

city_cache = {}

@app.post('/trade')
def trade():
    data = request.get_json()
    city_name = data.get("message").strip().title()
    
    city_data = connection.execute(select(
        city.c.name,
        city.c.population,
        city.c.description,
        city.c.image).where(city.c.name == city_name)).mappings().first()
    if city_data is None:
        return jsonify({"error": "Try another city, please."})
    
    if city_data['name'] in city_cache and time() - city_cache[city_data['name']]['temporal']['cache_time'] < 3600:
        temperature = city_cache[city_data['name']]['temporal']['temperature']
        print('cache instead')
    elif city_data['name'] in city_cache and time() - city_cache[city_data['name']]['temporal']['cache_time'] >= 3600:
        latitude = city_cache[city_data['name']]['latitude']
        longitude = city_cache[city_data['name']]['longitude']
        temperature = temperature_api(city_cache, city_data['name'], latitude=latitude, longitude=longitude, time_passed=True)
    else:
        temperature = temperature_api(city_cache, city_data['name'])
    return jsonify({
        "name": city_data['name'], #anti xss fuckers
        "population": city_data["population"],
        "description": city_data["description"],
        "image": city_data["image"],
        "temperature": temperature,
        "visible": True
        }
                   )

@app.post('/delete')
def delete_account():
    token = request.cookies.get("token")
    try:
        data = jwt.decode(token, KEY, algorithms="HS256")
        user_id = data["user_id"]
        print(user_id)
        delete = connection.execute(users.delete().where(users.c.id == user_id))
        connection.commit()
        response = make_response(redirect(url_for("main")))
        response.delete_cookie("token")
        return response
    except jwt.ExpiredSignatureError:
        response = make_response(redirect(url_for("login")))
        response.delete_cookie("token")
        return response
    except jwt.InvalidTokenError:
        response = make_response(redirect(url_for("main")))
        response.delete_cookie("token")
        return response
