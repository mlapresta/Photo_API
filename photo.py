from google.cloud import datastore
from flask import Flask, request, jsonify, Blueprint, make_response
import datetime
import json
import constants
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
from google.auth.transport import requests
from google.oauth2 import id_token

client = datastore.Client()

bp = Blueprint('photo', __name__, url_prefix='/photos')

photo_errors = {
    "400_partial":{"Error": "There is an issue with one of the attributes, no attributes sent, or additional attributes sent."},
    "400_required": {"Error": "The request object is missing at least one of the required attributes, there is an issue with one of the required attributes, or additional attributes sent."},
    "400_duplicate": {"Error": "The photo is already tagged with that tag_id."},
    "401": {"Error": "No credentials provided or provided credentials invalid."},
    "403": {"Error": "Credentials provided do not have access to this photo"},
    "404": {"Error": "No photo with this photo_id exists"},
    "404_put": {"Error": "No photo with this photo_id exists and/or no tag with this tag_id exists"},
    "404_delete": {"Error": "No photo with this photo_id exists and/or no tag with this tag_id exists, or this photo was not tagged by this tag_id"},
    "405": {"Error" : "Method Not Allowed"},
    "406": {"Error": "Unsupported MIME type sent in request Accept Header or no Accept Header sent."},
    "409": {"Error": "The url specified in the request object is already taken."},
    "415": {"Error": "Only application/json acceptable."}
}
url_valid_characters = ["-", "_", ".", "~", "!", "*", "'", "(", ")", ";", ":", "@", "&", "=", "+", "$", ",", "/", "?", "%", "#", "[", "]" ]
photo_attributes = ["url", "description", "date" ]
date_format = '%Y-%m-%d'
CLIENT_ID = '174243479293-stg0oqthgeor34ea8afn4j6pn93s25c8.apps.googleusercontent.com'


@bp.route('', methods=['POST','GET'])
def photos_get_post():
    if request.method == 'POST':
        if no_401(request.headers.get('Authorization')) == False:
            res = make_response(json.dumps(photo_errors["401"]))
            res.mimetype = 'application/json'
            res.status_code = 401
            return res

        auth = request.headers.get('Authorization').split()
        jwt=auth[1]
        ownerID = verify_jwt(jwt)

        content = request.get_json()
        if request.content_type and 'application/json' not in request.content_type:
            res = make_response(json.dumps(photo_errors["415"]))
            res.mimetype = 'application/json'
            res.status_code = 415
            return res
        if 'application/json' != request.headers['Accept']:
            res = make_response(json.dumps(photo_errors["406"]))
            res.mimetype = 'application/json'
            res.status_code = 406
            return res

        if content == None or len(content.keys()) != 3:
            print("len")
            res = make_response(json.dumps(photo_errors["400_required"]))
            res.mimetype = 'application/json'
            res.status_code = 400
            return res
        for field in content.keys():
            if field not in photo_attributes:
                print("missing field")
                res = make_response(json.dumps(photo_errors["400_required"]))
                res.mimetype = 'application/json'
                res.status_code = 400
                return res
            if verify_photo(content[field], field) == False:
                print("verify")
                res = make_response(json.dumps(photo_errors["400_required"]))
                res.mimetype = 'application/json'
                res.status_code = 400
                return res

        query = client.query(kind=constants.photos)
        query.add_filter("owner", "=", ownerID["sub"])
        results = list(query.fetch())
        for e in results:
            if e["url"].lower() == content["url"].lower():
                res = make_response(json.dumps(photo_errors["409"]))
                res.mimetype = 'application/json'
                res.status_code = 409
                return res

        new_photo = datastore.entity.Entity(key=client.key(constants.photos))
        new_photo.update({
            "url": content["url"],
            "description": content["description"],
            "date": content["date"],
            "tags": [],
            "owner": ownerID["sub"],
        })
        client.put(new_photo)
        result = client.get(key=new_photo.key)
        #add id, and self, and send data back to user
        result["id"] = str(new_photo.key.id)
        result["self"] = request.url_root + "photos/" + str(new_photo.key.id)
        print("New photo added:")
        print(result)
        #return created photo
        res = make_response(json.dumps(result))
        res.mimetype = 'application/json'
        res.status_code = 201
        return res


    elif request.method == 'GET':
        if no_401(request.headers.get('Authorization')) == False:
            res = make_response(json.dumps(photo_errors["401"]))
            res.mimetype = 'application/json'
            res.status_code = 401
            return res

        auth = request.headers.get('Authorization').split()
        jwt=auth[1]
        ownerID = verify_jwt(jwt)

        content = request.get_json()
        if 'application/json' != request.headers['Accept']:
            res = make_response(json.dumps(photo_errors["406"]))
            res.mimetype = 'application/json'
            res.status_code = 406
            return res

        query = client.query(kind=constants.photos)
        query.add_filter("owner", "=", ownerID["sub"])
        q_limit = int(request.args.get('limit', '5'))
        q_offset = int(request.args.get('offset', '0'))
        l_iterator = query.fetch(limit= q_limit, offset=q_offset)
        pages = l_iterator.pages
        results = list(next(pages))
        if l_iterator.next_page_token:
            next_offset = q_offset + q_limit
            next_url = request.base_url + "?limit=" + str(q_limit) + "&offset=" + str(next_offset)
        else:
            next_url = None
        for e in results:
            e["id"] = e.key.id
            if "tags" in e.keys():
                for tag in e["tags"]:
                    tag["self"] = request.url_root + "tags/" + tag["id"]
            else:
                e["tags"] = []
            e["self"] = request.url_root + "photos/" + str(e.key.id)
        output = {"photos": results}
        if next_url:
            output["next"] = next_url

        query = client.query(kind=constants.photos)
        query.add_filter("owner", "=", ownerID["sub"])
        output["count"] = len(list(query.fetch()))
        res = make_response(json.dumps(output))
        res.mimetype = 'application/json'
        res.status_code = 200
        return res
    else:
        res = make_response(json.dumps(photo_errors["405"]))
        res.mimetype = 'application/json'
        res.status_code = 405
        return res



@bp.route('/<photo_id>', methods=['GET','DELETE', 'PATCH', 'PUT'])
def photo_get_delete_patch_put(photo_id):
    if request.method == 'GET':
        if no_401(request.headers.get('Authorization')) == False:
            res = make_response(json.dumps(photo_errors["401"]))
            res.mimetype = 'application/json'
            res.status_code = 401
            return res
        auth = request.headers.get('Authorization').split()
        jwt=auth[1]
        ownerID = verify_jwt(jwt)

        if 'application/json' != request.headers['Accept']:
            res = make_response(json.dumps(photo_errors["406"]))
            res.mimetype = 'application/json'
            res.status_code = 406
            return res
        photo = get_photo(photo_id, ownerID["sub"])
        #tag_key = client.key(constants.tags, int(tag_id))
        #tag = client.get(key=tag_key)
        #if tag not found, return 404
        if photo == None:
            res = make_response(json.dumps(photo_errors["404"]))
            res.mimetype = 'application/json'
            res.status_code = 404
            return res

        if photo == -1:
            res = make_response(json.dumps(photo_errors["403"]))
            res.mimetype = 'application/json'
            res.status_code = 403
            return res
        '''
        tag["id"] = str(tag.key.id)
        tag["self"] = request.url_root + "tags/" + str(tag.key.id)
        if "photos" in tag.keys():
            for photo in tag["photos"]:
                photo["self"] = request.url_root + "photos/" + photo["id"]
        else:
            tag["photos"] = []
        '''
        res = make_response(json.dumps(photo))
        res.mimetype = 'application/json'
        res.status_code = 200
        return res


    elif request.method == 'PATCH':
        if no_401(request.headers.get('Authorization')) == False:
            res = make_response(json.dumps(photo_errors["401"]))
            res.mimetype = 'application/json'
            res.status_code = 401
            return res
        auth = request.headers.get('Authorization').split()
        jwt=auth[1]
        ownerID = verify_jwt(jwt)

        content = request.get_json()
        if request.content_type and 'application/json' not in request.content_type:
            print(request.content_type)
            res = make_response(json.dumps(photo_errors["415"]))
            res.mimetype = 'application/json'
            res.status_code = 415
            return res
        if 'application/json' != request.headers['Accept']:
            res = make_response(json.dumps(photo_errors["406"]))
            res.mimetype = 'application/json'
            res.status_code = 406
            return res

        if content == None:
            res = make_response(json.dumps(photo_errors["400_partial"]))
            res.mimetype = 'application/json'
            res.status_code = 400
            return res
        for field in content.keys():
            if field not in photo_attributes:
                res = make_response(json.dumps(photo_errors["400_partial"]))
                res.mimetype = 'application/json'
                res.status_code = 400
                return res
            if verify_photo(content[field], field) == False:
                res = make_response(json.dumps(photo_errors["400_partial"]))
                res.mimetype = 'application/json'
                res.status_code = 400
                return res
        if "url" in content.keys():
            query = client.query(kind=constants.photos)
            query.add_filter("owner", "=", ownerID["sub"])
            results = list(query.fetch())
            for e in results:
                print(e)
                if e["url"].lower() == content["url"].lower() and e.key.id != int(photo_id):
                    res = make_response(json.dumps(photo_errors["409"]))
                    res.mimetype = 'application/json'
                    res.status_code = 409
                    return res

        photo = get_photo(photo_id, ownerID["sub"], False)
        #tag_key = client.key(constants.tags, int(tag_id))
        #tag = client.get(key=tag_key)
        #if tag not found, return 404
        if photo == None:
            res = make_response(json.dumps(photo_errors["404"]))
            res.mimetype = 'application/json'
            res.status_code = 404
            return res

        if photo == -1:
            res = make_response(json.dumps(photo_errors["403"]))
            res.mimetype = 'application/json'
            res.status_code = 403
            return res

        for key in content.keys():
            photo[key] = content[key]
        client.put(photo)

        photo = get_photo(photo_id, ownerID["sub"])

        '''
        result = client.get(key=tag_key)
        #add id, self to data sent back to user
        tag["id"] = str(tag.key.id)
        tag["self"] = request.url_root + "tags/" + str(tag.key.id)
        if "photos" in tag.keys():
            for photo in tag["photos"]:
                photo["self"] = request.url_root + "photos/" + photo["id"]
        else:
            tag["photos"] = []
        '''
        res = make_response(json.dumps(photo))
        res.mimetype = 'application/json'
        res.status_code = 200
        return res


    elif request.method == 'PUT':
        if no_401(request.headers.get('Authorization')) == False:
            res = make_response(json.dumps(photo_errors["401"]))
            res.mimetype = 'application/json'
            res.status_code = 401
            return res
        auth = request.headers.get('Authorization').split()
        jwt=auth[1]
        ownerID = verify_jwt(jwt)

        content = request.get_json()
        if request.content_type and 'application/json' not in request.content_type:
            res = make_response(json.dumps(photo_errors["415"]))
            res.mimetype = 'application/json'
            res.status_code = 415
            return res
        if 'application/json' != request.headers['Accept']:
            res = make_response(json.dumps(photo_errors["406"]))
            res.mimetype = 'application/json'
            res.status_code = 406
            return res

        if content == None or len(content.keys()) != 3:
            res = make_response(json.dumps(photo_errors["400_required"]))
            res.mimetype = 'application/json'
            res.status_code = 400
            return res
        for field in content.keys():
            if field not in photo_attributes:
                res = make_response(json.dumps(photo_errors["400_required"]))
                res.mimetype = 'application/json'
                res.status_code = 400
                return res
            if verify_photo(content[field], field) == False:
                res = make_response(json.dumps(photo_errors["400_required"]))
                res.mimetype = 'application/json'
                res.status_code = 400
                return res

        query = client.query(kind=constants.photos)
        query.add_filter("owner", "=", ownerID["sub"])
        results = list(query.fetch())
        for e in results:
            if e["url"].lower() == content["url"].lower() and e.key.id != int(photo_id):
                res = make_response(json.dumps(photo_errors["409"]))
                res.mimetype = 'application/json'
                res.status_code = 409
                return res

        photo = get_photo(photo_id, ownerID["sub"], False)
        #tag_key = client.key(constants.tags, int(tag_id))
        #tag = client.get(key=tag_key)
        #if tag not found, return 404
        if photo == None:
            res = make_response(json.dumps(photo_errors["404"]))
            res.mimetype = 'application/json'
            res.status_code = 404
            return res

        if photo == -1:
            res = make_response(json.dumps(photo_errors["403"]))
            res.mimetype = 'application/json'
            res.status_code = 403
            return res

        for key in content.keys():
            photo[key] = content[key]
        client.put(photo)

        photo = get_photo(photo_id, ownerID["sub"])

        '''
        result = client.get(key=tag_key)
        #add id, self to data sent back to user
        tag["id"] = str(tag.key.id)
        tag["self"] = request.url_root + "tags/" + str(tag.key.id)
        if "photos" in tag.keys():
            for photo in tag["photos"]:
                photo["self"] = request.url_root + "photos/" + photo["id"]
        else:
            tag["photos"] = []
        '''
        res = make_response(json.dumps(photo))
        res.mimetype = 'application/json'
        res.status_code = 200
        return res

    elif request.method == 'DELETE':
        if no_401(request.headers.get('Authorization')) == False:
            res = make_response(json.dumps(photo_errors["401"]))
            res.mimetype = 'application/json'
            res.status_code = 401
            return res
        auth = request.headers.get('Authorization').split()
        jwt=auth[1]
        ownerID = verify_jwt(jwt)

        photo = get_photo(photo_id, ownerID["sub"], False)
        #tag_key = client.key(constants.tags, int(tag_id))
        #tag = client.get(key=tag_key)
        #if tag not found, return 404
        if photo == None:
            res = make_response(json.dumps(photo_errors["404"]))
            res.mimetype = 'application/json'
            res.status_code = 404
            return res
        if photo == -1:
            res = make_response(json.dumps(photo_errors["403"]))
            res.mimetype = 'application/json'
            res.status_code = 403
            return res

        photo_key = client.key(constants.photos, int(photo_id))
        #if "tags" in photo.keys():
        for t in photo["tags"]:
            tag_key = client.key(constants.tags, int(t["id"]))
            tag = client.get(key=tag_key)
            for p in range(len(tag["photos"])):
                if tag["photos"][p]["id"] == photo_id:
                    del tag["photos"][p]
                    break
            client.put(tag)
        print(photo_key)
        client.delete(photo_key)
        photo = get_photo(photo_id, ownerID["sub"], False)
        print(photo)
        return '',204
    else:
        res = make_response(json.dumps(photo_errors["405"]))
        res.mimetype = 'application/json'
        res.status_code = 405
        return res


@bp.route('/<photo_id>/tags/<tag_id>', methods=['PUT', 'DELETE'])
def photo_put_delete_tag(photo_id, tag_id):
    if request.method == 'PUT':
        if no_401(request.headers.get('Authorization')) == False:
            res = make_response(json.dumps(photo_errors["401"]))
            res.mimetype = 'application/json'
            res.status_code = 401
            return res
        auth = request.headers.get('Authorization').split()
        jwt=auth[1]
        ownerID = verify_jwt(jwt)
        photo = get_photo(photo_id, ownerID["sub"], False)
        tag_key = client.key(constants.tags, int(tag_id))
        tag = client.get(key=tag_key)

        #tag_key = client.key(constants.tags, int(tag_id))
        #tag = client.get(key=tag_key)
        #if tag not found, return 404
        if photo == None or tag == None:
            res = make_response(json.dumps(photo_errors["404_put"]))
            res.mimetype = 'application/json'
            res.status_code = 404
            return res

        if photo == -1:
            res = make_response(json.dumps(photo_errors["403"]))
            res.mimetype = 'application/json'
            res.status_code = 403
            return res

        for tag_idx in photo["tags"]:
            if tag_idx["id"]==tag_id:
                res = make_response(json.dumps(photo_errors["400_duplicate"]))
                res.mimetype = 'application/json'
                res.status_code = 400
                return res
        photo["tags"].append({"id": tag_id, "name": tag["name"]})
        print(tag.keys())
        tag["photos"].append({"id":photo_id})
        client.put_multi([photo, tag])
        return '',204


    if request.method == 'DELETE':
        if no_401(request.headers.get('Authorization')) == False:
            res = make_response(json.dumps(photo_errors["401"]))
            res.mimetype = 'application/json'
            res.status_code = 401
            return res
        auth = request.headers.get('Authorization').split()
        jwt=auth[1]
        ownerID = verify_jwt(jwt)
        photo = get_photo(photo_id, ownerID["sub"], False)
        tag_key = client.key(constants.tags, int(tag_id))
        tag = client.get(key=tag_key)

        #tag_key = client.key(constants.tags, int(tag_id))
        #tag = client.get(key=tag_key)
        #if tag not found, return 404
        if photo == None or tag == None:
            res = make_response(json.dumps(photo_errors["404_delete"]))
            res.mimetype = 'application/json'
            res.status_code = 404
            return res
        tag_found = False
        if photo != -1:
            for t in photo["tags"]:
                if t["id"]==tag_id:
                    tag_found = True
                    break
            if tag_found == False:
                res = make_response(json.dumps(photo_errors["404_delete"]))
                res.mimetype = 'application/json'
                res.status_code = 404
                return res
        if photo == -1:
            res = make_response(json.dumps(photo_errors["403"]))
            res.mimetype = 'application/json'
            res.status_code = 403
            return res

        for t in range(len(photo["tags"])):
            if photo["tags"][t]["id"]==tag_id:
                del photo["tags"][t]
                break
        client.put(photo)

        for p in range(len(tag["photos"])):
            print(tag["photos"])
            print(p)
            if tag["photos"][p]["id"]==photo_id:
                del tag["photos"][p]
                break
        client.put(tag)
        return '',204





def get_photo(photo_id, owner, return_to_user = True):
    photo_key = client.key(constants.photos, int(photo_id))
    photo = client.get(key=photo_key)
    print(photo)
    if photo == None:
        return None
    if photo["owner"]!= owner:
        return -1
    if return_to_user == True:
        #add id, self to data sent back to user
        photo["id"] = str(photo.key.id)
        photo["self"] = request.url_root + "photos/" + str(photo.key.id)

        if "tags" in photo.keys():
            for tag in photo["tags"]:
                tag["self"] = request.url_root + "tags/" + tag["id"]
        else:
            photo["tags"] = []
    return photo


def is_accepted_characters(input_string):
    return all(ord(c) >= 32 and ord(c)<=126 for c in input_string)


def verify_photo(user_input, field):
    if not isinstance(user_input, str):
        return False
    if field == "url":
        if 4 > len(user_input) or len(user_input) > 256:
            print("url len")
            return False
        for letter in user_input:
            if not letter.isalnum() and not (letter in url_valid_characters):
                print("letter")
                return False
    elif field == "description":
        if 1 > len(user_input) or len(user_input) > 256:
            print("desc len")
            return False
        if is_accepted_characters(user_input) == False:
            print("desc char")
            return False
    elif field == "date":
        if len(user_input)!= 10:
            print("date len")
            return False
        try:
            date_obj = datetime.datetime.strptime(user_input, date_format)
        except ValueError:
            print("date invalid")
            return False
    else:
        return True


def no_401(user_authorization):
    if user_authorization == None:
        return False
    if user_authorization.startswith('Bearer '):
        auth = request.headers.get('Authorization').split()
        jwt=auth[1]
    else:
        return False
    #if missing or invalid JWT
    if jwt == None:
        return False
    ownerID = verify_jwt(jwt)
    if ownerID == None or ownerID == -1:
        return False
    return True


def verify_jwt(jwt):
    try:
        req = requests.Request()
        id_info = id_token.verify_oauth2_token(
        jwt, req, CLIENT_ID)
        return(id_info)
    except ValueError:
        return(None)
    except:
        print("Unexpected Error")
        return -1
