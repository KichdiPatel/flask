from flask import Flask, render_template
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest
import pandas as pd
from datetime import datetime
from sqlalchemy.dialects.postgresql import ARRAY
import datetime as dt
from datetime import datetime, timezone
from sqlalchemy import Boolean
from threading import Timer
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import os
from dotenv import load_dotenv
import plaid
from plaid.api import plaid_api
import logging
import psycopg2
from psycopg2 import OperationalError

# Set up logging
logging.basicConfig(level=logging.INFO)

# Load environment variables from the .env file
load_dotenv()

# Load environment variables
# plaid variables
PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")
PLAID_ENV = os.getenv("PLAID_ENV", "production")
PLAID_PRODUCTS = os.getenv("PLAID_PRODUCTS", "transactions").split(",")
PLAID_COUNTRY_CODES = os.getenv("PLAID_COUNTRY_CODES", "US").split(",")
PLAID_WEBHOOK_URL = os.getenv("PLAID_WEBHOOK_URL")
PLAID_REDIRECT_URI = os.getenv("PLAID_REDIRECT_URI")
PLAID_CLIENT_NAME = os.getenv("PLAID_CLIENT_NAME", "YourAppName")
PORT = 5000

# database variable
DATABASE_URL = os.getenv("DATABASE_URL")
print(DATABASE_URL)

# twilio variables
ACCOUNT_SID = os.getenv("ACCOUNT_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")
USER_PHONE_NUM = os.getenv("USER_PHONE_NUM")
TWILIO_NUM = os.getenv("TWILIO_NUM")

# Verify the DATABASE_URL
if not DATABASE_URL:
    logging.error("DATABASE_URL is not set or is empty.")
    exit(1)

# Set up the Plaid environment
host = (
    plaid.Environment.Sandbox
    if PLAID_ENV == "sandbox"
    else plaid.Environment.Production
)

# Configure the Plaid client
configuration = plaid.Configuration(
    host=host,
    api_key={
        "clientId": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
        "plaidVersion": "2020-09-14",
    },
)

api_client = plaid.ApiClient(configuration)
client = plaid_api.PlaidApi(api_client)

products = [Products(product) for product in PLAID_PRODUCTS]

# Initialize Flask application
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
CORS(app)

# Test database connection
try:
    connection = psycopg2.connect(DATABASE_URL)
    cursor = connection.cursor()
    cursor.execute("SELECT version();")
    db_version = cursor.fetchone()
    logging.info(f"Connected to PostgreSQL, version: {db_version}")
except OperationalError as e:
    logging.error(f"Error connecting to the database: {e}")
    exit(1)
finally:
    if connection:
        cursor.close()
        connection.close()

# Initialize SQLAlchemy
try:
    db = SQLAlchemy(app)
    logging.info("Database initialized successfully.")
except Exception as e:
    logging.error(f"Error initializing the database: {e}")
    logging.error(f"Exception details: {e.__class__.__name__}: {e}")
    exit(1)

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(port=PORT)
