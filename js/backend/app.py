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
from datetime import datetime, timedelta
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
CORS(app, resources={r"/*": {"origins": "https://shelf-mate-pages.vercel.app"}})

# Upload folder for books
UPLOAD_FOLDER = '/tmp/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # Set maximum file size to 20MB

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
users_table = dynamodb.Table('users')


# s3 connection
s3 = boto3.client(
    's3',
    aws_access_key_id='',
    aws_secret_access_key='',
)

BUCKET_NAME = 'shelfmate-bucket'


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
        "last_sign_in_date": None,
        "reading_positions": {}
    }

    # Insert user document into DynamoDB
    users_table.put_item(Item=user_document)

    try:
        # Create a folder (prefix) for the user in S3 bucket
        s3.put_object(Bucket=BUCKET_NAME, Key=f'{user_data["username"]}/')
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
            'exp': datetime.utcnow() + timedelta(hours=24)
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
# Author: Antonios Tsolis [https://github.com/doduykhang/epub-cover-extract]
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
@cross_origin() 
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


# Endpoint to save the user's reading position
@app.route('/saveReadingPosition', methods=['POST'])
@cross_origin()
def save_reading_position():
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

    logging.debug('Save reading position endpoint called')

    try:
        request_data = request.get_json()
        if not request_data or 'filename' not in request_data or 'position' not in request_data:
            logging.error('Filename or position not provided')
            return jsonify({"error": "Missing request or filename and reading_position data"}), 400

        filename = request_data['filename']
        position = request_data['position']

        # Update the reading_position attribute
        response = users_table.update_item(
            Key={'username': username},
            UpdateExpression='SET reading_positions.#filename = :position',
            ExpressionAttributeNames={'#filename': filename},
            ExpressionAttributeValues={':position': position},
            ReturnValues='UPDATED_NEW'
        )
        
        logging.debug(f'Update response: {response}')
        return jsonify({'message': 'Reading position saved successfully'}), 200

    except Exception as e:
        logging.error(f'Error saving reading position: {e}')
        return jsonify({'error': str(e)}), 500
    

# Endpoint to get the user's reading position
@app.route('/getReadingPosition', methods=['GET'])
@cross_origin()
def get_reading_position():
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

    filename = request.args.get('filename')

    if not filename:
        return jsonify({'error': 'Filename not provided'}), 400

    try:
        # Initialize DynamoDB resource
        table = users_table

        # Get the item from DynamoDB
        response = table.get_item(
            Key={'username': username},
            ProjectionExpression="reading_positions.#filename",
            ExpressionAttributeNames={'#filename': filename}
        )

        # Check if the item and attribute exist in the response
        if 'Item' in response and 'reading_positions' in response['Item']:
            reading_positions = response['Item']['reading_positions']
            if filename in reading_positions:
                reading_position = int(reading_positions[filename])
                return jsonify({'filename': filename, 'reading_position': reading_position}), 200
            else:
                return jsonify({'error': 'Reading position for the file not found'}), 404
        else:
            return jsonify({'error': 'User or reading positions not found'}), 404
    except Exception as e:
        logging.error(f'Error fetching reading position: {e}')
        return jsonify({'error': str(e)}), 500

 

####### GAMIFICATION ENDPOINTS #######

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
        current_date = datetime.utcnow().date()

        if last_sign_in_date:
            last_sign_in_date = datetime.strptime(last_sign_in_date, "%Y-%m-%d").date()
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
            elif current_date - last_sign_in_date == timedelta(days=1):
                # Continuing streak
                if pages_read > 0:
                    streak = current_streak + 1
                    points = Decimal(str(pages_read * ((streak / 2) + 1)))
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
            # If user has read a page, increment streak and points
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
@cross_origin() 
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
@cross_origin() 
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
@cross_origin() 
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
@cross_origin() 
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
@cross_origin() 
def get_book_details(book_id):
    response = requests.get(GOOGLE_BOOKS_API_BASE_URL + f'/volumes/{book_id}', params={
        'key': API_KEY
    })
    if response.status_code == 200:
        return jsonify(response.json())
    else:
        return jsonify({"error": f"Failed to get book details for ID: {book_id}"}), response.status_code


### Job Schedulers ###
# Flask-Mail configuration for Namecheap Private Email
app.config['MAIL_SERVER'] = 'mail.privateemail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = 'shelfpal@shelfmate-app.online'
app.config['MAIL_PASSWORD'] = 'Seeu@the2p'
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_DEFAULT_SENDER'] = 'shelfpal@shelfmate-app.online'

mail = Mail(app)

# Initialize the scheduler
scheduler = BackgroundScheduler()

def send_reminder_emails():
    today = datetime.now(pytz.utc).strftime('%Y-%m-%d')
    response = users_table.scan(
        FilterExpression=(
            Attr('last_sign_in_date').eq(None) | 
            Attr('last_sign_in_date').lt(str(today))
        )
    )
    users_to_remind = response.get('Items', [])

    with app.app_context():
        for user in users_to_remind:
            msg = Message(
                'Keep the Streak Alive, Mate – Dive Back into the App! 🔆',
                recipients=[user['email']]
            )
            msg.body = f"Hi {user['name']},\n\nThis is a reminder to sign in to your shelfMate account and read a book today! \n\nRemember, every page you read brings you closer to new badges, leaderboard levels, and fun reading adventures! \n\n\nHappy reading, \n\nYour pal from shelfMate :)"
            try:
                mail.send(msg)
                logging.debug(f'Sent reminder to {user["email"]}')
            except Exception as e:
                logging.error(f"Failed to send email to {user['email']}: {str(e)}")


def reset_streak():
    today = datetime.now(pytz.utc).strftime('%Y-%m-%d')
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    # Scan the table for users
    response = users_table.scan()
    users = response.get('Items', [])
    logging.debug(f"Users to check for streak reset: {users}")

    for user in users:
        last_sign_in = user.get('last_sign_in_date')
        if last_sign_in and last_sign_in != yesterday:
            users_table.update_item(
                Key={'username': user['username']},
                UpdateExpression='SET streak = :val',
                ExpressionAttributeValues={':val': 0}
            )
            logging.debug(f"Reset streak for {user['username']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        # Schedule the jobs only if they are not already scheduled
        if not any(job.name == "send_reminder_emails" for job in scheduler.get_jobs()):
            scheduler.add_job(func=send_reminder_emails, trigger='cron', hour=17, minute=30, timezone='UTC', id='send_reminder_emails')
            logging.debug("Scheduled job 'send_reminder_emails'")

        if not any(job.name == "reset_streak" for job in scheduler.get_jobs()):
            scheduler.add_job(func=reset_streak, trigger='cron', hour=1, minute=00, timezone='UTC', id='reset_streak')
            logging.debug("Scheduled job 'reset_streak'")

        scheduler.start()

    try:
        app.run(debug=True, host='0.0.0.0', port=8080)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
