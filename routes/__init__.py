import json
import os
import uuid
from urllib.parse import unquote

import requests
import spotipy
from flask import request, redirect, session, render_template, Blueprint

from utils import session_cache_uuid_path, add_remove_job, remove_songs


routes = Blueprint('routes', __name__)


@routes.route('/playlist/restrict')
def remove_n_songs():
    playlist_id = request.args['playlist_id']
    n = int(request.args.get('n', 20))
    user = request.args.get('user')
    add_remove_job(n, playlist_id, user)
    return remove_songs(n, playlist_id, user, session_cache_path=session_cache_uuid_path)


@routes.route('/playlists')
def playlists():
    cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=session_cache_uuid_path())
    auth_manager = spotipy.oauth2.SpotifyOAuth(cache_handler=cache_handler)

    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        return redirect('/')

    if not session.get('n'):
        return render_template('input_max.html')

    spotify = spotipy.Spotify(auth_manager=auth_manager)
    user_playlists = []
    r = spotify.current_user_playlists(limit=50)
    user_playlists.extend(r['items'])
    offset = 50

    while r['next']:
        r = spotify.current_user_playlists(offset=offset, limit=50)
        user_playlists.extend(r['items'])
        offset += 50

    playlist_name_id = {unquote(x['name']): x['id'] for x in user_playlists}
    user = current_user()['id']

    return render_template('list_elements.html', data=playlist_name_id.items(), n=session['n'], user=user)


@routes.route('/playlists', methods=['POST'])
def playlists_post():
    session['n'] = int(request.form['n'])
    return redirect('/playlists')


@routes.route('/sign_out')
def sign_out():
    try:
        # Remove the CACHE file (.cache-test) so that a new user can authorize.
        os.remove(session_cache_uuid_path())
        session.clear()
    except OSError as e:
        print("Error: %s - %s." % (e.filename, e.strerror))
    return redirect('/')


@routes.route('/')
def index():
    if not session.get('uuid'):
        # Step 1. Visitor is unknown. Try known and then give random ID
        session['uuid'] = str(uuid.uuid4())

    cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=session_cache_uuid_path())
    auth_manager = spotipy.oauth2.SpotifyOAuth(
        scope='user-read-currently-playing playlist-modify-private playlist-modify-public playlist-read-collaborative',
        cache_handler=cache_handler,
        show_dialog=True
    )

    if request.args.get("code"):
        # Step 3. Being redirected from Spotify auth page
        auth_manager.get_access_token(request.args.get("code"))
        return redirect('/')

    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        # Step 2. Display sign in link when no token
        auth_url = auth_manager.get_authorize_url()
        return f'<h2><a href="{auth_url}">Sign in</a></h2>'

    # Step 4. Signed in, save token and display data

    # upload to json storage with user as key
    bin_id = os.environ.get('BIN_ID')
    r = requests.get('https://json.extendsclass.com/bin/%s' % bin_id)
    data = json.loads(r.json())
    data[current_user()['id']] = cache_handler.get_cached_token()
    r = requests.put(
        'https://json.extendsclass.com/bin/%s' % bin_id,
        json=json.dumps(data),
    )
    if r.status_code > 300:
        return {'error': r.text}

    spotify = spotipy.Spotify(auth_manager=auth_manager)
    return f'<h2>Hi {spotify.me()["display_name"]}, ' \
           f'<small><a href="/sign_out">[sign out]<a/></small></h2>' \
           f'<a href="/playlists">restrict playlists</a> | ' \
           f'<a href="/reset_playlists">reset playlists</a> | ' \
           f'<a href="/currently_playing">currently playing</a> | ' \
           f'<a href="/current_user">me</a>'


@routes.route('/current_user')
def current_user():
    cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=session_cache_uuid_path())
    auth_manager = spotipy.oauth2.SpotifyOAuth(cache_handler=cache_handler)
    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        return redirect('/')
    spotify = spotipy.Spotify(auth_manager=auth_manager)
    return spotify.current_user()