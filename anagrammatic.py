import os
from flask import Flask, render_template, request, jsonify, session
import random
from datetime import timedelta

app = Flask(__name__)
app.config['ENV'] = os.environ.get('FLASK_ENV', 'development')
app.config['DEBUG'] = app.config['ENV'] == 'development'
# Set a secret key for session management - in production, use a secure random key
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev_key_replace_in_production')
# Set session to expire after 24 hours of inactivity
app.permanent_session_lifetime = timedelta(days=1)

# Load words from a file
def load_words():
    try:
        with open("words.txt") as f:
            words = set(word.strip().lower() for word in f if len(word.strip()) > 2)
        return words
    except FileNotFoundError:
        return set()

# Get a random 9-letter word
def get_nine_letter_word(word_list):
    nine_letter_words = [word for word in word_list if len(word) == 9]
    return random.choice(nine_letter_words) if nine_letter_words else None

word_list = load_words()
nine_letter_word = get_nine_letter_word(word_list)
letters = list(nine_letter_word)
random.shuffle(letters)
found_words = set()
score = 0  # Initialize score

# Scoring system: 
# 3 letters = 100 points
# 4 letters = 400 points
# 5 letters = 800 points
# 6 letters = 1400 points
# 7 letters = 1800 points
# 8 letters = 2200 points
# 9 letters = 5000 points
SCORING = {
    3: 100,
    4: 400,
    5: 800,
    6: 1400,
    7: 1800,
    8: 2200,
    9: 5000
}

def init_game_state():
    """Initialize or reset game state"""
    nine_letter_word = get_nine_letter_word(word_list)
    letters = list(nine_letter_word)
    random.shuffle(letters)
    return {
        'nine_letter_word': nine_letter_word,
        'letters': letters,
        'current_letters': ''.join(letters).upper(),
        'found_words': [],
        'score': 0
    }

@app.route('/')
def index():
    # Make session permanent (but still expires after permanent_session_lifetime)
    session.permanent = True
    
    # Initialize session state if needed
    if 'game_state' not in session:
        session['game_state'] = init_game_state()
    
    game_state = session['game_state']
    return render_template("index.html", 
                         letters=game_state['current_letters'],
                         score=game_state['score'],
                         foundWords=game_state['found_words'])

@app.route('/shuffle', methods=['POST'])
def shuffle():
    game_state = session['game_state']
    letters_list = list(game_state['current_letters'])
    random.shuffle(letters_list)
    shuffled_letters = ''.join(letters_list)
    game_state['current_letters'] = shuffled_letters
    session.modified = True
    return jsonify({'letters': shuffled_letters})

@app.route('/check', methods=['POST'])
def check_word():
    game_state = session['game_state']
    data = request.get_json()
    word = data.get("word", "").strip().lower()
    
    def create_response(status, message):
        return jsonify({
            "status": status,
            "message": message,
            "score": game_state['score'],
            "foundWords": game_state['found_words']
        })
    
    if word == game_state['nine_letter_word']:
        game_state['score'] += SCORING[9]
        session.modified = True
        return create_response("win", "You found the 9-letter word!")
    
    if word not in word_list:
        return create_response("invalid", f"{word.upper()} not found in dictionary")
    
    if not all(word.count(letter) <= game_state['nine_letter_word'].count(letter) for letter in set(word)):
        return create_response("invalid", f"Can't make {word.upper()} with these letters")
    
    if word.upper() in game_state['found_words']:
        return create_response("duplicate", f"Already found {word.upper()}")
    
    word_length = len(word)
    if word_length >= 3:
        points = SCORING.get(word_length, 0)
        game_state['score'] += points
        game_state['found_words'].append(word.upper())
        session.modified = True
        return create_response("valid", f"Found: {word.upper()}! (+{points} points)")
    else:
        return create_response("invalid", "Words must be at least 3 letters long")

@app.route('/new-game', methods=['POST'])
def new_game():
    session['game_state'] = init_game_state()
    game_state = session['game_state']
    return jsonify({
        'letters': game_state['current_letters'],
        'score': game_state['score'],
        'foundWords': game_state['found_words']
    })

if __name__ == '__main__':
    # Only use debug mode when running locally
    app.run(host='0.0.0.0', 
           port=int(os.environ.get('PORT', 10000)),
           debug=app.config['DEBUG'])
