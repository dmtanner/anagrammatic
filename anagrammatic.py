from flask import Flask, render_template, request, jsonify
import random

app = Flask(__name__)

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

# Initialize CURRENT_LETTERS with the shuffled nine_letter_word
CURRENT_LETTERS = ''.join(letters).upper()

@app.route('/')
def index():
    global CURRENT_LETTERS, score
    if CURRENT_LETTERS is None:
        # If somehow CURRENT_LETTERS is None, reinitialize it
        letters = list(nine_letter_word)
        random.shuffle(letters)
        CURRENT_LETTERS = ''.join(letters).upper()
    return render_template("index.html", letters=CURRENT_LETTERS, score=score)

@app.route('/shuffle', methods=['POST'])
def shuffle():
    global CURRENT_LETTERS
    letters_list = list(CURRENT_LETTERS)
    random.shuffle(letters_list)
    shuffled_letters = ''.join(letters_list)
    CURRENT_LETTERS = shuffled_letters
    return jsonify({'letters': shuffled_letters})

@app.route('/check', methods=['POST'])
def check_word():
    global score
    data = request.get_json()
    word = data.get("word", "").strip().lower()
    
    # Create response with found words
    def create_response(status, message):
        return jsonify({
            "status": status,
            "message": message,
            "score": score,
            "foundWords": list(found_words)  # Convert set to list for JSON
        })
    
    if word == nine_letter_word:
        score += SCORING[9]
        return create_response("win", "You found the 9-letter word!")
    
    if word not in word_list:
        return create_response("invalid", f"{word.upper()} not found in dictionary")
    
    if not all(word.count(letter) <= letters.count(letter) for letter in set(word)):
        return create_response("invalid", f"Can't make {word.upper()} with these letters")
    
    if word in found_words:
        return create_response("duplicate", f"Already found {word.upper()}")
    
    word_length = len(word)
    if word_length >= 3:
        points = SCORING.get(word_length, 0)
        score += points
        found_words.add(word.upper())  # Store words in uppercase
        return create_response("valid", f"Found: {word.upper()}! (+{points} points)")
    else:
        return create_response("invalid", "Words must be at least 3 letters long")

if __name__ == '__main__':
    app.run(debug=True)
