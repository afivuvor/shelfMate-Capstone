import os
import io
import sys
import jwt
import pytz 
import boto3
import bcrypt
import epublib
import zipfile
import logging
import requests
import datetime
import mailersend
import PIL as pillow
from PIL import Image
from io import BytesIO
from lxml import etree
from zipfile import ZipFile
from flask_cors import CORS
from decimal import Decimal
from mailersend import emails
from datetime import timedelta
from bson.objectid import ObjectId
from urllib.parse import quote_plus
from flask_cors import cross_origin
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
from boto3.dynamodb.conditions import Key, Attr
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, request, jsonify, send_file
from apscheduler.schedulers.background import BackgroundScheduler


app = Flask(__name__)
CORS(app)

# Upload folder for PDFs
UPLOAD_FOLDER = '/tmp/uploads'
BUCKET_NAME = ''
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload directory exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
    logging.debug(f'Created upload directory: {UPLOAD_FOLDER}')

# Google Books API
GOOGLE_BOOKS_API_BASE_URL = "https://www.googleapis.com/books/v1"
API_KEY = ""


# DB connection
dynamodb = boto3.resource(
    'dynamodb',
    aws_access_key_id='',
    aws_secret_access_key='',
    region_name='eu-west-1'
)

# Reference to the 'users' table
users_table = dynamodb.Table('')


# s3 connection
s3 = boto3.client(
    's3',
    aws_access_key_id='',
    aws_secret_access_key='',
)

BUCKET_NAME = ''


# Secret key for JWT
SECRET_KEY = ''
if not SECRET_KEY:
    raise ValueError("No JWT_SECRET_KEY set for Flask application")


# Set up logging
# logging.basicConfig(level=logging.DEBUG)


# App Routes
@app.route("/signUp", methods=['POST'])
@cross_origin() 
def signUp():
    user_data = request.json
    if not user_data:
        return jsonify({"error": "Missing user data"}), 400

    # Check if user already exists
    response = users_table.get_item(Key={"username": user_data["username"]})
    if 'Item' in response:
        return jsonify({"error": "Username already exists"}), 400
    
    hashed_password = bcrypt.hashpw(user_data["password"].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    user_data["password"] = hashed_password

    # Create the user document with default values for additional fields
    user_document = {
        "username": user_data["username"],
        "name": user_data["name"],
        "email": user_data["email"],
        "gender": user_data["gender"],
        "password": user_data["password"],
        "occupation": user_data["occupation"],
        "badges": [],
        "streak": 0,
        "points": 0,
        "leaderboard_position": 0,
        "link_to_catalogue": "",
        "last_sign_in_date": None
    }

    # Insert user document into DynamoDB
    users_table.put_item(Item=user_document)

    try:
        # Create a folder (prefix) for the user in S3 bucket
        s3.put_object(Bucket='shelfmate-books', Key=f'{user_data["username"]}/')
        return jsonify({"message": "User created successfully", "username": user_data["username"]}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/signIn", methods=['POST'])
@cross_origin()
def signIn():
    try:
        user_data = request.json
        logging.debug(f"Received user data: {user_data}")
        if not user_data or "username" not in user_data or "password" not in user_data:
            return jsonify({"error": "Missing username or password"}), 400

        username = user_data.get('username')
        password = user_data.get('password')

        # Fetch user from DynamoDB
        logging.debug(f"Fetching user: {username}")
        response = users_table.get_item(Key={"username": username})
        if 'Item' not in response:
            logging.debug("User not found")
            return jsonify({"error": "Invalid username or password"}), 400

        user_item = response['Item']
        logging.debug(f"User item: {user_item}")
        if not bcrypt.checkpw(password.encode('utf-8'), user_item["password"].encode('utf-8')):
            logging.debug("Password mismatch")
            return jsonify({"error": "Invalid username or password"}), 400

        token = jwt.encode({
            'username': username,
            'exp': datetime.datetime.utcnow() + timedelta(hours=24)
        }, SECRET_KEY, algorithm='HS256')
        logging.debug(f"Generated token: {token}")
        return jsonify({"message": "Sign in successful", "token": token}), 200
    except Exception as e:
        logging.error(f"Error during sign in: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
    

# Profile information
@app.route("/getUserProfile", methods=['GET'])
@cross_origin()
def getUserProfile():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401

    # Initialize booksRead
    booksRead = 0

    token = auth_header.split(" ")[1]
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        username = data['username']
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token has expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    
    try:
        booksresponse = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=f'{username}/')

        # Check if the 'Contents' key is in the response
        if 'Contents' in booksresponse:
            # Get the length of the contents
            booksRead = len(booksresponse['Contents']) - 1
    except Exception as e:
        return jsonify({"error": str(e)})

    try:
        response = users_table.get_item(Key={'username': username})
        if 'Item' not in response:
            return jsonify({"error": "User not found"}), 404

        user_data = response['Item']
        profile_data = {
            "username": user_data.get('username'),
            "email": user_data.get('email'),
            "gender": user_data.get('gender'),
            "points": user_data.get('points', 0),
            "badges": user_data.get('badges', []),
            "streak": user_data.get('streak', 0),
            "booksRead": booksRead
        }
        return jsonify(profile_data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

# Endpoint to upload a PDF to user's folder in S3
@app.route('/upload', methods=['POST'])
@cross_origin()
def upload_file():
    logging.debug('Upload endpoint called')
    if 'file' not in request.files or 'username' not in request.form:
        logging.error('No file or username provided')
        return jsonify({'error': 'No file or username provided'}), 400

    file = request.files['file']
    username = request.form['username']
    if file.filename == '' or not username:
        logging.error('No selected file or username')
        return jsonify({'error': 'No selected file or username'}), 400

    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        logging.debug(f'Saving file to {file_path}')
        try:
            file.save(file_path)
            logging.debug(f'File saved to {file_path}')

            # Upload file to user's folder in S3 bucket
            s3.upload_file(file_path, 
                           BUCKET_NAME, 
                           f'{username}/{filename}')
            logging.debug(f'File uploaded to S3 at {username}/{filename}')
            
            # Optionally, save metadata or database record linking user and file
            return jsonify({'message': 'File uploaded successfully'}), 200
        except Exception as e:
            logging.error(f'Error uploading file: {e}')
            return jsonify({'error': str(e)}), 500
        finally:
            # Clean up: remove the temporary file
            if os.path.exists(file_path):
                os.remove(file_path)
                logging.debug(f'Temporary file {file_path} removed')
            else:
                logging.error(f'Temporary file {file_path} not found for removal')


# Endpoint to fetch user's files from S3
@app.route('/userFiles', methods=['GET'])
@cross_origin()
def list_user_files():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401

    token = auth_header.split(" ")[1]
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        username = data['username']
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token has expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    
    if not username:
        return jsonify({'error': 'Username not provided'}), 400

    response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=f'{username}/')
    files = []
    for obj in response.get('Contents', []):
        files.append({
            'name': obj['Key'].split('/')[-1],
            'url': f'https://{BUCKET_NAME}.s3.eu-west-1.amazonaws.com/{obj["Key"]}',
            'lastModified': obj['LastModified'].isoformat()
        })

    return jsonify(files)


# Endpoints to get epub images
namespaces = {
    "calibre": "http://calibre.kovidgoyal.net/2009/metadata",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "opf": "http://www.idpf.org/2007/opf",
    "u": "urn:oasis:names:tc:opendocument:xmlns:container",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "xhtml": "http://www.w3.org/1999/xhtml"
}

def get_epub_cover(epub_path):
    with zipfile.ZipFile(epub_path) as z:
        t = etree.fromstring(z.read("META-INF/container.xml"))
        rootfile_path = t.xpath("/u:container/u:rootfiles/u:rootfile", namespaces=namespaces)[0].get("full-path")
        t = etree.fromstring(z.read(rootfile_path))

        cover_href = None
        try:
            cover_id = t.xpath("//opf:metadata/opf:meta[@name='cover']", namespaces=namespaces)[0].get("content")
            cover_href = t.xpath("//opf:manifest/opf:item[@id='" + cover_id + "']", namespaces=namespaces)[0].get("href")
        except IndexError:
            pass

        if not cover_href:
            try:
                cover_href = t.xpath("//opf:manifest/opf:item[@properties='cover-image']", namespaces=namespaces)[0].get("href")
            except IndexError:
                pass

        if not cover_href:
            try:
                cover_page_id = t.xpath("//opf:spine/opf:itemref", namespaces=namespaces)[0].get("idref")
                cover_page_href = t.xpath("//opf:manifest/opf:item[@id='" + cover_page_id + "']", namespaces=namespaces)[0].get("href")
                cover_page_path = os.path.join(os.path.dirname(rootfile_path), cover_page_href)
                t = etree.fromstring(z.read(cover_page_path))
                cover_href = t.xpath("//xhtml:img", namespaces=namespaces)[0].get("src")
            except IndexError:
                pass

        if not cover_href:
            print("Cover image not found.")
            return None

        cover_path = os.path.join(os.path.dirname(rootfile_path), cover_href)
        return z.open(cover_path)


@app.route('/epub_cover', methods=['POST'])
def epub_cover():
    epub_file = request.files['file']
    epub_path = os.path.join('/tmp', epub_file.filename)
    epub_file.save(epub_path)

    cover = get_epub_cover(epub_path)
    if not cover:
        return jsonify({'error': 'Cover image not found'}), 404

    image = Image.open(cover)
    image_byte_arr = io.BytesIO()
    image.save(image_byte_arr, format='PNG')
    image_byte_arr.seek(0)

    os.remove(epub_path)
    return send_file(image_byte_arr, mimetype='image/png')
    

####### GAMIFICATION ENDPOINTS #######
# Reset streaks endpoint if user fails to read in a day
def reset_streak():
    # Calculate the dates
    today = datetime.datetime.utcnow().date()
    yesterday = today - timedelta(days=1)

    # Scan the table for users
    response = users_table.scan()
    users = response.get('Items', [])

    # Iterate over users and reset streak if needed
    for user in users:
        last_sign_in = user.get('last_sign_in_date')
        if last_sign_in and last_sign_in != str(yesterday):
            # Update the user's streak to 0
            users_table.update_item(
                Key={'username': user['username']},
                UpdateExpression='SET streak = :val',
                ExpressionAttributeValues={':val': 0}
            )

# Set up the scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=reset_streak, trigger='cron', hour=00, minute=0)


# Update streaks and points endpoint
@app.route("/updateStreakAndPoints", methods=['POST'])
@cross_origin()
def update_streak_and_points():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401

    token = auth_header.split(" ")[1]
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        username = data['username']
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token has expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401

    streak_data = request.json
    if not streak_data or 'pages_read' not in streak_data or 'daily_sign_in' not in streak_data:
        return jsonify({"error": "Missing streak or pages_read data"}), 400

    pages_read = streak_data.get('pages_read')
    daily_sign_in = streak_data.get('daily_sign_in')

    try:
        response = users_table.get_item(Key={"username": username})
        if 'Item' not in response:
            return jsonify({"error": "User not found"}), 404

        user_item = response['Item']
        current_streak = user_item.get('streak', 0)
        last_sign_in_date = user_item.get('last_sign_in_date')
        current_date = datetime.datetime.utcnow().date()

        if last_sign_in_date:
            last_sign_in_date = datetime.datetime.strptime(last_sign_in_date, "%Y-%m-%d").date()
            if current_date == last_sign_in_date:
                # Already signed in today
                streak = current_streak
                if pages_read > 0:
                    # Only update points if pages_read > 0
                    points = Decimal(str(pages_read * (streak / 2 + 1)))
                    users_table.update_item(
                        Key={'username': username},
                        UpdateExpression="set points = points + :p",
                        ExpressionAttributeValues={':p': points}
                    )
                else:
                    points = 0
            elif current_date - last_sign_in_date == datetime.timedelta(days=1):
                # Continuing streak
                if pages_read > 0:
                    streak = current_streak + 1
                    points = Decimal(str(pages_read * (streak / 2 + 1)))
                    users_table.update_item(
                        Key={'username': username},
                        UpdateExpression="set streak = :s, points = points + :p, last_sign_in_date = :d",
                        ExpressionAttributeValues={
                            ':s': streak,
                            ':p': points,
                            ':d': str(current_date)
                        }
                    )
                else:
                    streak = 0
                    points = 0
            else:
                # Streak broken
                streak = 0
                points = 0
                users_table.update_item(
                    Key={'username': username},
                    UpdateExpression="set streak = :s, last_sign_in_date = :d",
                    ExpressionAttributeValues={
                        ':s': streak,
                        ':d': str(current_date)
                    }
                )
        else:
            # First sign-in after sign-up, update last_sign_in_date to current date
            if pages_read > 0:
                streak = 1
                points = Decimal(str(pages_read * (streak / 2 + 1)))
                users_table.update_item(
                    Key={'username': username},
                    UpdateExpression="set streak = :s, points = :p, last_sign_in_date = :d",
                    ExpressionAttributeValues={
                        ':s': streak,
                        ':p': points,
                        ':d': str(current_date)
                    }
                )
            else:
                streak = 0
                points = 0

        # Fetch updated user data to get the new points value
        response = users_table.get_item(Key={"username": username})
        user_item = response['Item']
        updated_points = user_item.get('points', 0)
    except Exception as e:
        logging.error(f"Error updating streak and points: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

    return jsonify({"message": "Streak and points updated successfully", "points": updated_points}), 200


# Update badges endpoint
@app.route("/updateBadges", methods=['POST'])
@cross_origin()
def update_badges():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401

    token = auth_header.split(" ")[1]
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        username = data['username']
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token has expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401

    badge_data = request.json
    if not badge_data or 'badge' not in badge_data:
        return jsonify({"error": "Missing badge data"}), 400

    badge = badge_data.get('badge')

    try:
        response = users_table.get_item(Key={"username": username})
        if 'Item' not in response:
            return jsonify({"error": "User not found"}), 404

        user_item = response['Item']
        badges = user_item.get('badges', [])

        if badge not in badges:
            badges.append(badge)
            users_table.update_item(
                Key={'username': username},
                UpdateExpression="set badges = :b",
                ExpressionAttributeValues={':b': badges}
            )
    except Exception as e:
        logging.error(f"Error updating badges: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

    return jsonify({"message": "Badge updated successfully"}), 200


# Leaderboard endpoint
@app.route("/leaderboard", methods=['GET'])
@cross_origin()
def leaderboard():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401

    token = auth_header.split(" ")[1]
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token has expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401

    try:
        # Scan the users table and sort by points in descending order
        response = users_table.scan()
        users = response.get('Items', [])
        sorted_users = sorted(users, key=lambda x: int(x.get('points', 0)), reverse=True)

        # Only return necessary fields
        leaderboard_data = [{
            "username": user.get("username"),
            "points": int(user.get("points", 0)),
            "badges": user.get("badges", [])
        } for user in sorted_users]

        return jsonify(leaderboard_data), 200
    except Exception as e:
        logging.error(f"Error fetching leaderboard: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
    

# Reminders
# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



############################################################################################################
# Search books endpoints
@app.route("/search", methods=['GET'])
def search_books():
    query = request.args.get("q")
    if not query:
        return jsonify({"error": "Missing 'q' parameter"}), 400

    params = {
        "q": query,
        "key": API_KEY,
        "maxResults": 20  
    }
    response = requests.get(GOOGLE_BOOKS_API_BASE_URL + "/volumes", params=params)

    if response.status_code == 200:
        data = response.json()
        return jsonify(data)
    else:
        return jsonify({"error": "Unable to search for book"}), response.status_code


@app.route("/search/<isbn>")
def get_book_data(isbn):
    params = {
        "q": f"isbn:{isbn}",
        "key": API_KEY
    }
    response = requests.get(GOOGLE_BOOKS_API_BASE_URL + "/volumes", params=params)

    if response.status_code == 200:
        data = response.json()
        return jsonify(data)
    else:
        return jsonify({"error": "Unable to search for book"}), response.status_code


@app.route("/search/author", methods=['GET'])
def get_author():
    query = request.args.get("q")
    if not query:
        return jsonify({"error": "Missing 'q' parameter"}), 400

    params = {
        "q": f"inauthor:{query}",
        "key": API_KEY,
        "maxResults": 20  
    }
    response = requests.get(GOOGLE_BOOKS_API_BASE_URL + "/volumes", params=params)
    
    if response.status_code == 200:
        data = response.json()
        return jsonify(data)
    else:
        return jsonify({"error": "Unable to search for book"}), response.status_code

    
@app.route("/category/<category_name>")
def get_books_by_category(category_name):
    params = {
        "q": f"subject:{category_name}",
        "key": API_KEY,
        "maxResults": 40  
    }
    response = requests.get(GOOGLE_BOOKS_API_BASE_URL + "/volumes", params=params)

    if response.status_code == 200:
        data = response.json()
        return jsonify(data)
    else:
        return jsonify({"error": "Unable to search for book"}), response.status_code


@app.route('/book/<book_id>')
def get_book_details(book_id):
    response = requests.get(GOOGLE_BOOKS_API_BASE_URL + f'/volumes/{book_id}', params={
        'key': API_KEY
    })
    if response.status_code == 200:
        return jsonify(response.json())
    else:
        return jsonify({"error": f"Failed to get book details for ID: {book_id}"}), response.status_code


if __name__ == "__main__":
    app.run(debug=True, port=(8080))
    