from google.cloud import datastore
from flask import Flask, request, jsonify, make_response, session, url_for, redirect, render_template, _request_ctx_stack, Blueprint
import json
import constants
import requests
import hashlib
import os
import json
import tag
import photo
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
from google.auth.transport import requests
from google.oauth2 import id_token

#Note: modeled after OPENID connect flow
app = Flask(__name__)
app.register_blueprint(tag.bp)
app.register_blueprint(photo.bp)


client = datastore.Client()
app.secret_key = b'?Y\x1cU\xd6D\xd7\xee\x0bgB\x16\xe0a\xfaP'
CLIENT_SECRETS_FILE="client_secret_174243479293-stg0oqthgeor34ea8afn4j6pn93s25c8.apps.googleusercontent.com.json"
CLIENT_ID = '174243479293-stg0oqthgeor34ea8afn4j6pn93s25c8.apps.googleusercontent.com'
SCOPES = ['openid profile email']
tag_types = ["company", "hashtag", "location"]

os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
required_parameters = {"boat": ["name", "type", "length"], "slip": ["number"]}

class AuthError(Exception):
    def __init__(self, error, status_code):
        self.error = error
        self.status_code = status_code

@app.errorhandler(AuthError)
def handle_auth_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    return response

@app.route('/')
def index():
    if 'credentials' not in session:
        return render_template("welcome.html")
    # Load credentials from the session.
    credentials = google.oauth2.credentials.Credentials(
      **session['credentials'])

    print(credentials.id_token)

    # Save credentials back to session in case access token was refreshed.
    # ACTION ITEM: In a production app, you likely want to save these
    #              credentials in a persistent database instead.
    #session['credentials'] = credentials_to_dict(credentials)
    script = ["script.js"]
    user_id = verify_jwt(credentials.id_token)

    #look for duplicate boat name, if duplicate found, return 403 error
    query = client.query(kind=constants.users)
    query.add_filter("sub", "=", user_id['sub'])
    results = list(query.fetch())
    #if not found, add to database
    if len(results) == 0:
        new_user = datastore.entity.Entity(key=client.key(constants.users))
        new_user.update({"sub": user_id['sub'], "email": user_id['email']})
        client.put(new_user)
    return render_template("User_Info.html", jsscripts = script, jwt=credentials.id_token, user_id = user_id['sub'], user_email=user_id['email'])


@app.route('/login')
def login():
    # Create flow instance to manage the OAuth 2.0 Authorization Grant Flow steps.
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
      CLIENT_SECRETS_FILE, scopes=SCOPES)

    # Generate and Store the state so the callback can verify the auth server response.
    state = hashlib.sha256(os.urandom(1024)).hexdigest()
    print(f"state:{state}")
    session['state'] = state

    # The URI created here must exactly match one of the authorized redirect URIs
    # for the OAuth 2.0 client, which you configured in the API Console. If this
    # value doesn't match an authorized URI, you will get a 'redirect_uri_mismatch'
    # error.
    flow.redirect_uri = url_for('oauth2callback', _external=True)

    authorization_url, state = flow.authorization_url(
      # Enable offline access so that you can refresh an access token without
      # re-prompting the user for permission. Recommended for web server apps.
      access_type='offline',
      state = state,
      # Enable incremental authorization. Recommended as a best practice.
      include_granted_scopes='true')

    print(f"authorization_url {authorization_url}")
    print(f"state: {state}")
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    # Specify the state when creating the flow in the callback so that it can
    # verified in the authorization server response.
    SCOPES = ['openid profile email']
    # Ensure that the request is not a forgery and that the user sending
    # this connect request is the expected user.
    if request.args.get('state', '') != session['state']:
      response = make_response(json.dumps('Invalid state parameter.'), 401)
      response.headers['Content-Type'] = 'application/json'
      return response

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES)
    flow.redirect_uri = url_for('oauth2callback', _external=True)
    # Use the authorization server's response to fetch the OAuth 2.0 tokens.
    authorization_response = request.url
    flow.fetch_token(authorization_response=authorization_response)
    print(f"authorization_res:{authorization_response}")
    # Store credentials in the session.
    # ACTION ITEM: In a production app, you likely want to save these
    #              credentials in a persistent database instead.
    credentials = flow.credentials
    session['credentials'] = credentials_to_dict(credentials)
    print(f"id_toke: {credentials.id_token}")
    return redirect(url_for('index'))

@app.route('/clear')
def clear():
    session.clear()
    return redirect(url_for('index'))


@app.route('/verify-jwt')
def verify():
    req = requests.Request()

    id_info = id_token.verify_oauth2_token(
    request.args['jwt'], req, CLIENT_ID)
    print(id_info['sub'])
    return repr(id_info) + "<br><br> the user is: " + id_info['email']


@app.route('/users', methods=['GET'])
def users_get():
    if request.method == 'GET':
        if 'application/json' != request.headers['Accept']:
            error = {"Error": "Unsupported MIME type sent in request Accept Header or no Accept Header sent."}
            res = make_response(json.dumps(error))
            res.mimetype = 'application/json'
            res.status_code = 406
            return res
        query = client.query(kind=constants.users)
        results = list(query.fetch())
        output = {"users": results}
        output["count"]=len(results)
        res = make_response(json.dumps(output))
        res.mimetype = 'application/json'
        res.status_code = 200
        return res
    else:
        return 'Method not recogonized'



def credentials_to_dict(credentials):
    return {'token': credentials.token,
          'refresh_token': credentials.refresh_token,
          'token_uri': credentials.token_uri,
          'client_id': credentials.client_id,
          'client_secret': credentials.client_secret,
          'scopes': credentials.scopes,
          'id_token': credentials.id_token}

def verify_jwt(jwt):
    try:
        print(jwt)
        req = requests.Request()

        id_info = id_token.verify_oauth2_token(
        jwt, req, CLIENT_ID)
        print(repr(id_info))
        print(id_info['sub'])
        print(id_info['email'])
        return(id_info)
    except ValueError:
        return(None)
    except:
        print("Unexpected Error")
        return -1



@app.errorhandler(404)
def page_not_found(error):
    error = {"Error": "The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again."}
    res = make_response(json.dumps(error))
    res.mimetype = 'application/json'
    res.status_code = 404
    return res

@app.errorhandler(405)
def page_not_found(error):
    error = {"Error": "Unsupported method at this URL."}
    res = make_response(json.dumps(error))
    res.mimetype = 'application/json'
    res.status_code = 405
    return res

if __name__ == '__main__':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    app.run(host='127.0.0.1', port=8080, debug=True)
