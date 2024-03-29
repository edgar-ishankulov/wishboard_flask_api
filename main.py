import os
import json
import bcrypt
from dotenv import load_dotenv
import requests
from flask_cors import CORS
from flask import Flask, jsonify, request, url_for, redirect, Blueprint
from datetime import datetime, timedelta, timezone
from flask_jwt_extended import (
    create_access_token,
    get_jwt,
    get_jwt_identity,
    unset_jwt_cookies,
    JWTManager,
)
import pymongo
from pymongo import MongoClient
from bson.json_util import dumps
from flask_mail import Mail, Message
from itsdangerous import SignatureExpired, URLSafeTimedSerializer
from new_image import new_image_blueprint
from crud_operations import crud_operations_blueprint

load_dotenv(dotenv_path="./.env.local")

UNSPLASH_URL = "https://api.unsplash.com/photos/random/"

FRONTEND_HOST = os.environ.get("FRONTEND_HOST")
DB_HOST = os.environ.get("DB_HOST")
UNSPLASH_KEY = os.environ.get("UNSPLASH_KEY", "")
DEBUG = bool(os.environ.get("DEBUG", True))
client = pymongo.MongoClient(DB_HOST)

if not UNSPLASH_KEY:
    raise EnvironmentError(
        "Please create .env.local file and insert UNSPLASH_KEY there"
    )

app = Flask(__name__)

app.register_blueprint(new_image_blueprint, url_prefix="")
app.register_blueprint(crud_operations_blueprint, url_prefix="")

CORS(app)
serializer = URLSafeTimedSerializer("SecretKey")
app.config["DEBUG"] = DEBUG
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=12)

app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 465
app.config["MAIL_USE_SSL"] = True
app.config["MAIL_USE_TLS"] = False
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")



# Token Management

jwt = JWTManager(app)
@app.after_request
def refresh_expiring_jwts(response):
    try:
        exp_timestamp = get_jwt()["exp"]
        now = datetime.now(timezone.utc)
        target_timestamp = datetime.timestamp(now +timedelta(minutes=30) )
        if target_timestamp > exp_timestamp:
            access_token = create_access_token(identity=get_jwt_identity())
            data = response.get_json()
            if type(data) is dict:
                data["access_token"] = access_token 
                response.data = json.dumps(data)
        return response
    except (RuntimeError, KeyError):
        return response
        
@app.route("/logout", methods=["POST"])
def logout():
    response = jsonify({"msg": "logout successful"})
    unset_jwt_cookies(response)
    return response

@app.route("/token", methods=["POST"])
def create_token():
    db = client["images-db"]
    usersCollection = db["users"]
    email = request.json.get("email", None)
    password = request.json.get("password", None)
    salt = bcrypt.gensalt()
    user = usersCollection.find_one({"email": email}, {'_id': 0})
    if user == None:
        return {"msg": "Wrong email or password"}, 401
    if email != user['email'] or bcrypt.checkpw(password.encode('utf-8'), user['password']) != True: #nosec
        print (bcrypt.checkpw(password.encode('utf-8'), user['password']))
        return {"msg": "Wrong email or password"}, 401
    if (user['is_verified'] == False):
        return {"msg": "Account not verified"}, 402

    additional_claims = {"user": email}
    access_token = create_access_token(identity=email, additional_claims=additional_claims)
    response = {"access_token": access_token, "user": user}
    print(response)
    return dumps(response)

mail = Mail(app)

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        request_data = request.get_json()
        db = client["images-db"]
        usersCollection = db["users"]
        email = request_data['email']
        name = request_data['name']
        userInDb = usersCollection.find_one({"email": email})
        if not userInDb:
            emailToken = serializer.dumps(email)
            msg = Message('Confirm Email', sender='edgar.ishankulov@gmail.com', recipients=[email])
            link = url_for('confirm_email', emailToken=emailToken, _external=True)
            msg.body = 'Hi {}! Thank you for using Wishboard. Please follow this link to verify your account {}'.format(name,link)
            mail.send(msg)
            salt = bcrypt.gensalt()
            password = bcrypt.hashpw(request_data['password'].encode('utf-8'), salt)
            passwordAsString = password.decode('utf-8')
            print(password)

            user = {
            'name': name,
            'email': email, 
            'password': password,
            'is_verified': False
            }
    
            usersCollection.insert_one(user)
            return "User signed up successfully with token" + emailToken, 200
        if email == userInDb['email']:
            return "User already exists", 403

@app.route("/confirm_email/<emailToken>")
def confirm_email(emailToken):
    try:
        db = client["images-db"]
        usersCollection = db["users"]
        email = serializer.loads(emailToken)
        print(email)
        user = usersCollection.find_one({'email': email})
        if (email == user['email']):
            usersCollection.find_one_and_update({'email': email}, { '$set': {'is_verified': True}})
            return redirect(FRONTEND_HOST, )
    except SignatureExpired:
        return "The token expired"



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050) #nosec
    # app.run(host="192.168.0.171", port=8080) #nosec
