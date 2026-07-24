from flask import Flask, render_template, request, jsonify
from sqlalchemy import create_engine, Table, Column, Integer, String, MetaData, select
from os import getenv
from dotenv import load_dotenv
import psycopg2
from requests import get

load_dotenv()
DB = getenv('DB_URL')

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
        
app = Flask(__name__)

@app.errorhandler(404)
def not_found(e):
    return render_template('error.html')

@app.route('/')
def main():
    return render_template('index.html')

@app.route('/trade', methods=["POST"])
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
    latitude = geo['results'][0]['latitude']
    longitude = geo['results'][0]['longitude']
    
    weather = get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m"
            }
        ).json()

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
