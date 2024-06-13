import jwt
import boto3
import bcrypt
import logging
import requests
import datetime
from decimal import Decimal
from flask_cors import CORS
from flask_cors import cross_origin
from bson.objectid import ObjectId
from flask import Flask, request, jsonify
from urllib.parse import quote_plus
from boto3.dynamodb.conditions import Key, Attr

app = Flask(__name__)
CORS(app)

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

# Secret key for JWT
SECRET_KEY = ''
if not SECRET_KEY:
    raise ValueError("No JWT_SECRET_KEY set for Flask application")


# Reference to the 'users' table
users_table = dynamodb.Table('users')


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
    return jsonify({"message": "User registered successfully", "username": user_data["username"]}), 201


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
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, SECRET_KEY, algorithm='HS256')
        logging.debug(f"Generated token: {token}")
        return jsonify({"message": "Sign in successful", "token": token}), 200
    except Exception as e:
        logging.error(f"Error during sign in: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


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
            elif current_date - last_sign_in_date == datetime.timedelta(days=1):
                # Continuing streak
                if pages_read > 0:
                    streak = current_streak + 1
                else:
                    streak = 0
            else:
                # Streak broken
                streak = 0
        else:
            # First sign-in after sign-up, update last_sign_in_date to current date
            if pages_read > 0:
                streak = 1
                last_sign_in_date = current_date
            else:
                streak = 0

        # Calculate points only if pages_read is greater than 0
        if pages_read > 0:
            # Calculate points
            points = Decimal(str(pages_read * (streak / 2 + 1)))
        else:
            points = 0

        # Update user data if pages_read is greater than 0
        if pages_read > 0:
            users_table.update_item(
                Key={'username': username},
                UpdateExpression="set streak = :s, points = points + :p, last_sign_in_date = :d",
                ExpressionAttributeValues={
                    ':s': streak,
                    ':p': points,
                    ':d': str(current_date)
                }
            )
            
            # Fetch updated user data to get the new points value
            response = users_table.get_item(Key={"username": username})
            user_item = response['Item']
            updated_points = user_item.get('points', 0)
        else:
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


# # Update leaderboard position endpoint
# @app.route("/updateLeaderboardPosition", methods=['POST'])
# @cross_origin()
# def updateLeaderboardPosition():
#     auth_header = request.headers.get('Authorization')
#     if not auth_header or not auth_header.startswith("Bearer "):
#         return jsonify({"error": "Missing or invalid token"}), 401

#     token = auth_header.split(" ")[1]
#     try:
#         data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
#         username = data['username']
#     except jwt.ExpiredSignatureError:
#         return jsonify({"error": "Token has expired"}), 401
#     except jwt.InvalidTokenError:
#         return jsonify({"error": "Invalid token"}), 401

#     # Fetch user's points and badges
#     user_data = get_user_data(username)
#     points = user_data.get('points', 0)
#     badges = user_data.get('badges', [])

#     # Calculate leaderboard score
#     leaderboard_score = calculate_leaderboard_score(points, badges)

#     try:
#         response = users_table.update_item(
#             Key={'username': username},
#             UpdateExpression="set leaderboard_position = :l",
#             ExpressionAttributeValues={':l': leaderboard_score},
#             ReturnValues="UPDATED_NEW"
#         )
#     except Exception as e:
#         raise Exception("Error updating leaderboard position: " + str(e))
    
#     return jsonify({"message": "Leaderboard position updated successfully"}), 200


# # Helper functions for updating leaderboard position
# def get_user_data(username):
#     try:
#         response = users_table.get_item(
#             Key={'username': username}
#         )
#         user_data = response.get('Item')
#         if user_data:
#             return user_data
#         else:
#             raise Exception("User not found")
#     except Exception as e:
#         raise Exception("Error fetching user data: " + str(e))

# def calculate_leaderboard_score(points, badges):
#     # Define your logic to calculate the leaderboard score based on points and badges
#     leaderboard_score = points + len(badges)
#     return leaderboard_score


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
        username = data['username']
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token has expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401

    try:
        response = users_table.scan()  # Fetch all users from the database
        users = response.get('Items', [])
        
        # Sort users by points in descending order
        sorted_users = sorted(users, key=lambda user: user.get('points', 0), reverse=True)
        
        # Prepare leaderboard format to send to front-end
        leaderboard = [
            {
                "username": user.get("username"),
                "points": user.get("points", 0),
                "badges": ", ".join(user.get("badges", []))  # Join the array into a comma-separated string
            }
            for user in sorted_users
        ]
    except Exception as e:
        logging.error(f"Error retrieving leaderboard data: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

    return jsonify(leaderboard), 200


# Profile information
@app.route("/getUserProfile", methods=['GET'])
@cross_origin()
def getUserProfile():
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
            "badges": len(user_data.get('badges', [])),
            "streak": user_data.get('streak', 0),
            # Assuming you have a booksRead field in your database
            # "booksRead": user_data.get('booksRead', 0)
        }
        return jsonify(profile_data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    
