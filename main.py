from flask import Flask, render_template, request, jsonify
from sqlalchemy import create_engine, Table, Column, Integer, String, MetaData, select
from os import getenv
from dotenv import load_dotenv
import psycopg

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
    Column("description", String)
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
    population = connection.execute(select(city.c.population).where(city.c.name == city_name)).scalar()
    description = connection.execute(select(city.c.description).where(city.c.name == city_name)).scalar()
    if population is not None and description is not None:
        return jsonify({"name": city_name, "population": population, "description": description})
    return jsonify({"error": "Try another city, please."}), 404