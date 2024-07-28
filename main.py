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


# Database model
class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    access_token = db.Column(db.String(120), unique=True, nullable=False)
    item_id = db.Column(db.String(120), unique=True, nullable=False)
    cursor = db.Column(db.String(120), nullable=True)
    currentMonth = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    needsReconcile = db.Column(Boolean, nullable=False, default=False)
    currentlyReconciling = db.Column(Boolean, nullable=False, default=False)
    currentTx = db.Column(db.String(255), nullable=True)


class NewTx(db.Model):
    __tablename__ = "newTxs"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(255), nullable=False)
    category_id = db.Column(db.Integer, nullable=False)
    date = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class ApprovedTxs(db.Model):
    __tablename__ = "approvedTxs"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(255), nullable=False)
    category_id = db.Column(db.Integer, nullable=False)
    date = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


# Initialize the database
with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')


@app.route("/api/create_link_token", methods=["POST"])
def create_link_token():
    try:
        request = LinkTokenCreateRequest(
            client_name=PLAID_CLIENT_NAME,
            country_codes=[CountryCode(code) for code in PLAID_COUNTRY_CODES],
            language="en",
            user=LinkTokenCreateRequestUser(client_user_id="user"),
            products=products,
            webhook=PLAID_WEBHOOK_URL,
            redirect_uri=PLAID_REDIRECT_URI,
        )
        response = client.link_token_create(request)
        return jsonify(response.to_dict())
    except plaid.ApiException as e:
        print(json.loads(e.body))  # Debugging statement
        return jsonify(json.loads(e.body))


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    print(f"Webhook received: {json.dumps(data, indent=2)}")

    if "public_token" in data:
        public_token = data["public_token"]
        exchange_public_token(public_token)

    return jsonify(status="success"), 200


def exchange_public_token(public_token):
    try:
        exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
        exchange_response = client.item_public_token_exchange(exchange_request)
        access_token = exchange_response["access_token"]
        item_id = exchange_response["item_id"]

        # Save the access token and item ID in the database
        user = User.query.first()
        if user is None:
            user = User(
                access_token=access_token,
                item_id=item_id,
                currentMonth=datetime.now(),
                needsReconcile=False,
                currentlyReconciling=False,
            )
        else:
            user.access_token = access_token
            user.item_id = item_id
        db.session.add(user)
        db.session.commit()

        print(f"Access token: {access_token}")
        print(f"Item ID: {item_id}")
    except plaid.ApiException as e:
        print(json.loads(e.body))


if __name__ == "__main__":
    app.run(port=PORT, debug=True)
