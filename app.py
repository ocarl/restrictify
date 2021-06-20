from flask import Flask
from flask_session import Session
import os


app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(64)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = './.flask_session/'
Session(app)


from routes import routes
from commands import register


register(app)
app.register_blueprint(routes)

if __name__ == '__main__':
    app.run(
        threaded=True,
        port=int(os.environ.get("PORT",
                 os.environ.get("SPOTIPY_REDIRECT_URI", 8080).split(":")[-1])))
