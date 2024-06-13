from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os

app = Flask(__name__)
CORS(app)

GOOGLE_BOOKS_API_BASE_URL = "https://www.googleapis.com/books/v1"
API_KEY = ""

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
    
