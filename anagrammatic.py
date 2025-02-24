import os
from flask import Flask, render_template, request, jsonify, session
import random
from datetime import timedelta, datetime
from dataclasses import dataclass
import threading
import time
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config["ENV"] = os.environ.get("FLASK_ENV", "development")
app.config["DEBUG"] = app.config["ENV"] == "development"
# Set a secret key for session management - in production, use a secure random key
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_key_replace_in_production")
# Set session to expire after 24 hours of inactivity
app.permanent_session_lifetime = timedelta(days=1)
socketio = SocketIO(app)

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
    word = random.choice(nine_letter_words) if nine_letter_words else None
    print(f"Selected 9-letter word: {word}")
    return word


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
SCORING = {3: 100, 4: 400, 5: 800, 6: 1400, 7: 1800, 8: 2200, 9: 5000}


@dataclass
class Player:
    id: str
    score: int = 0
    found_words: list = None
    ready: bool = False
    name: str = None

    def __post_init__(self):
        if self.found_words is None:
            self.found_words = []


@dataclass
class GameRoom:
    id: str
    nine_letter_word: str
    current_letters: str
    players: dict  # player_id -> Player
    start_time: datetime = None
    game_duration: int = 120  # 2 minutes in seconds
    game_over: bool = False
    winner: str = None

    @property
    def is_full(self):
        return len(self.players) >= 2

    @property
    def all_players_ready(self):
        return len(self.players) == 2 and all(p.ready for p in self.players.values())

    @property
    def time_remaining(self):
        if not self.start_time:
            return self.game_duration
        elapsed = (datetime.now() - self.start_time).total_seconds()
        remaining = self.game_duration - elapsed
        # Round to nearest second to avoid stuttering
        return max(0, round(remaining))  # Changed from round(remaining, 1)

    def check_game_over(self):
        if self.game_over:
            return True
        if self.time_remaining <= 0:
            self.game_over = True
            # Find winner based on score
            players = list(self.players.values())
            if players[0].score > players[1].score:
                self.winner = list(self.players.keys())[0]
            elif players[1].score > players[0].score:
                self.winner = list(self.players.keys())[1]
            else:
                self.winner = "tie"
            return True
        return False


# Global game state
waiting_players = []  # List of player IDs waiting for a match
game_rooms = {}  # room_id -> GameRoom


def create_game_room():
    """Create a new game room with a unique nine-letter word"""
    room_id = str(random.randint(1000, 9999))
    nine_letter_word = get_nine_letter_word(word_list)
    letters = list(nine_letter_word)
    random.shuffle(letters)
    current_letters = "".join(letters).upper()

    return GameRoom(
        id=room_id,
        nine_letter_word=nine_letter_word,
        current_letters=current_letters,
        players={},
    )


def find_or_create_game(player_id):
    """Match player with waiting player or create new game"""
    print(
        f"Finding game for player {player_id}. Waiting players: {waiting_players}"
    )  # Debug print

    # First check if player is already in a game
    for game in game_rooms.values():
        if player_id in game.players:
            return game

    # Then try to match with a waiting player
    if waiting_players and player_id not in waiting_players:
        opponent_id = waiting_players.pop(0)
        print(f"Matching player {player_id} with {opponent_id}")  # Debug print

        game_room = create_game_room()
        game_room.players[opponent_id] = Player(id=opponent_id)
        game_room.players[player_id] = Player(id=player_id)
        game_rooms[game_room.id] = game_room
        return game_room

    # If no match found and not already waiting, add to waiting list
    if player_id not in waiting_players:
        print(f"Adding player {player_id} to waiting list")  # Debug print
        waiting_players.append(player_id)

    return None


@app.route("/")
def index():
    if "player_id" not in session:
        session["player_id"] = str(random.randint(10000, 99999))

    player_id = session["player_id"]

    # Check if player is already in a game
    for game_room in game_rooms.values():
        if player_id in game_room.players:
            player = game_room.players[player_id]
            return render_template(
                "index.html",
                session=session,
                current_game={
                    "room_id": game_room.id,
                    "letters": game_room.current_letters,
                    "score": player.score,
                    "found_words": player.found_words,
                    "time_remaining": game_room.time_remaining,
                    "game_started": game_room.start_time is not None,
                    "game_over": game_room.game_over,
                    "winner": game_room.winner,
                },
            )

    # No active game found
    return render_template("index.html", session=session, current_game=None)


@app.route("/join-game", methods=["POST"])
def join_game():
    player_id = session["player_id"]
    print(f"Join game request from player {player_id}")  # Debug print

    game_room = find_or_create_game(player_id)

    if game_room:
        return jsonify(
            {
                "status": "matched",
                "room_id": game_room.id,
                "letters": game_room.current_letters,
                "opponent": [
                    pid for pid in game_room.players.keys() if pid != player_id
                ][0],
            }
        )
    return jsonify({"status": "waiting", "message": "Waiting for opponent..."})


@socketio.on("connect")
def handle_connect():
    player_id = session.get("player_id")
    if not player_id:
        return False

    # Join player's personal room
    join_room(player_id)

    # If player is in a game, join game room
    for game_room in game_rooms.values():
        if player_id in game_room.players:
            join_room(game_room.id)
            emit_game_state(game_room)
            break


@socketio.on("disconnect")
def handle_disconnect():
    player_id = session.get("player_id")
    if not player_id:
        return

    # Find and leave any game rooms
    for game_room in game_rooms.values():
        if player_id in game_room.players:
            leave_room(game_room.id)
            # Optionally handle player disconnection
            break


def emit_game_state(game_room):
    """Emit current game state to all players in the room"""
    game_room.check_game_over()  # Update game over state

    for player_id, player in game_room.players.items():
        game_state = {
            "timeRemaining": game_room.time_remaining,
            "gameOver": game_room.game_over,
            "winner": game_room.winner,
            "scores": {
                pid: {"name": p.name or f"Player {pid[-4:]}", "score": p.score}
                for pid, p in game_room.players.items()
            },
            "score": player.score,
            "foundWords": player.found_words,
            "letters": game_room.current_letters,
            "roomId": game_room.id,
            "nineLetterWord": game_room.nine_letter_word.upper()
            if game_room.game_over
            else None,
        }

        print(f"Emitting state to {player_id}:", game_state)
        socketio.emit("game_state", game_state, room=player_id)


def game_state_loop(game_room):
    """Background task to emit game state updates"""
    while not game_room.game_over:
        emit_game_state(game_room)
        socketio.sleep(1.0)  # Changed from 0.1 to emit once per second


# Update ready endpoint to use WebSocket
@app.route("/ready", methods=["POST"])
def ready():
    player_id = session["player_id"]
    room_id = request.json.get("room_id")
    game_room = game_rooms.get(room_id)

    if not game_room or player_id not in game_room.players:
        return jsonify({"error": "Invalid game room"}), 400

    game_room.players[player_id].ready = True

    if game_room.all_players_ready:
        game_room.start_time = datetime.now()
        # Start game state emission
        socketio.start_background_task(game_state_loop, game_room)
        return jsonify({"status": "started", "timeRemaining": game_room.game_duration})

    return jsonify({"status": "waiting", "message": "Waiting for other player..."})


# Update the check_word route for multiplayer
@app.route("/check", methods=["POST"])
def check_word():
    try:
        player_id = session["player_id"]
        data = request.get_json()
        if not data:
            print("No JSON data received in check endpoint")
            return jsonify({"error": "No data received", "status": "error"}), 400

        room_id = data.get("room_id")
        if not room_id:
            print(f"No room_id provided by player {player_id}")
            return jsonify({"error": "No room ID provided", "status": "error"}), 400

        game_room = game_rooms.get(room_id)
        if not game_room:
            print(f"Invalid room {room_id} for player {player_id}")
            return jsonify({"error": "Invalid game room", "status": "error"}), 400

        if player_id not in game_room.players:
            print(f"Player {player_id} not in room {room_id}")
            return jsonify({"error": "Player not in game room", "status": "error"}), 400

        if game_room.check_game_over():
            emit_game_state(game_room)  # Emit final state
            return jsonify({"status": "game_over", "message": "Game is over"})

        player = game_room.players[player_id]
        word = data.get("word", "").strip().lower()

        print(f"Player {player_id} checking word '{word}' in room {room_id}")

        # Check word validity
        if word == game_room.nine_letter_word:
            player.score += SCORING[9]
            game_room.game_over = True
            game_room.winner = player_id
            emit_game_state(game_room)
            return jsonify(
                {
                    "status": "win",
                    "message": "You found the 9-letter word and won the game!",
                }
            )

        if word not in word_list:
            return jsonify(
                {
                    "status": "invalid",
                    "message": f"{word.upper()} not found in dictionary",
                }
            )

        if not all(
            word.count(letter) <= game_room.nine_letter_word.count(letter)
            for letter in set(word)
        ):
            return jsonify(
                {
                    "status": "invalid",
                    "message": f"Can't make {word.upper()} with these letters",
                }
            )

        if word.upper() in player.found_words:
            return jsonify(
                {"status": "duplicate", "message": f"Already found {word.upper()}"}
            )

        word_length = len(word)
        if word_length >= 3:
            points = SCORING.get(word_length, 0)
            player.score += points
            player.found_words.append(word.upper())
            emit_game_state(game_room)
            return jsonify(
                {
                    "status": "valid",
                    "message": f"Found: {word.upper()}! (+{points} points)",
                }
            )
        else:
            return jsonify(
                {
                    "status": "invalid",
                    "message": "Words must be at least 3 letters long",
                }
            )

    except Exception as e:
        print(f"Error in check_word: {e}")  # Debug print
        return jsonify({"status": "error", "message": "An error occurred"}), 500


@app.route("/new-game", methods=["POST"])
def new_game():
    player_id = session["player_id"]

    # Remove player from any existing game
    for room in list(game_rooms.values()):
        if player_id in room.players:
            del game_rooms[room.id]

    # Remove from waiting list if present
    if player_id in waiting_players:
        waiting_players.remove(player_id)

    # Start fresh matchmaking
    return jsonify({"status": "restart", "message": "Starting new game..."})


@app.route("/shuffle", methods=["POST"])
def shuffle():
    player_id = session["player_id"]
    room_id = request.json.get("room_id")
    game_room = game_rooms.get(room_id)

    if not game_room or player_id not in game_room.players:
        return jsonify({"error": "Invalid game room"}), 400

    letters_list = list(game_room.current_letters)
    random.shuffle(letters_list)
    shuffled_letters = "".join(letters_list)
    game_room.current_letters = shuffled_letters

    return jsonify({"letters": shuffled_letters})


@app.route("/update-name", methods=["POST"])
def update_name():
    player_id = session["player_id"]
    name = request.json.get("name", f"Player {player_id[-4:]}")

    # Store name in session
    session["player_name"] = name

    # Update name in any active game
    for game_room in game_rooms.values():
        if player_id in game_room.players:
            game_room.players[player_id].name = name
            emit_game_state(game_room)
            break

    return jsonify({"status": "success"})


if __name__ == "__main__":
    # Only use debug mode when running locally
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        debug=app.config["DEBUG"],
    )
