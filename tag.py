from google.cloud import datastore
from flask import Flask, request, jsonify, Blueprint, make_response
import json
import constants

client = datastore.Client()

bp = Blueprint('tag', __name__, url_prefix='/tags')

tag_errors = {
    "400_partial":{"Error": "There is an issue with one of the attributes, no attributes sent, or additional attributes sent."},
    "400_required": {"Error": "The request object is missing at least one of the required attributes, there is an issue with one of the required attributes, or additional attributes sent."},
    "404": {"Error": "No tag with this tag_id exists"},
    "405": {"Error" : "Method Not Allowed"},
    "406": {"Error": "Unsupported MIME type sent in request Accept Header or no Accept Header sent."},
    "409": {"Error": "The name specified in the request object is already taken."},
    "415": {"Error": "Only application/json acceptable."}
}

tag_attributes = ["name", "description", "type" ]
tag_types = ["company", "hashtag", "location"]

@bp.route('', methods=['POST','GET'])
def tags_get_post():
    if request.method == 'POST':
        content = request.get_json()
        if request.content_type and 'application/json' not in request.content_type:
            res = make_response(json.dumps(tag_errors["415"]))
            res.mimetype = 'application/json'
            res.status_code = 415
            return res
        if 'application/json' != request.headers['Accept']:
            res = make_response(json.dumps(tag_errors["406"]))
            res.mimetype = 'application/json'
            res.status_code = 406
            return res
        print(len(content.keys()))
        if content == None or len(content.keys()) != 3:
            res = make_response(json.dumps(tag_errors["400_required"]))
            res.mimetype = 'application/json'
            res.status_code = 400
            return res
        for field in content.keys():
            if field not in tag_attributes:
                res = make_response(json.dumps(tag_errors["400_required"]))
                res.mimetype = 'application/json'
                res.status_code = 400
                return res
            if verify_tag(content[field], field) == False:
                print(f"{field}fail")
                res = make_response(json.dumps(tag_errors["400_required"]))
                res.mimetype = 'application/json'
                res.status_code = 400
                return res

        query = client.query(kind=constants.tags)
        results = list(query.fetch())
        for e in results:
            if e["name"].lower() == content["name"].lower():
                res = make_response(json.dumps(tag_errors["409"]))
                res.mimetype = 'application/json'
                res.status_code = 409
                return res

        new_tag = datastore.entity.Entity(key=client.key(constants.tags))
        new_tag.update({
            "name": content["name"],
            "description": content["description"],
            "type": content["type"],
            "photos":[]
        })
        client.put(new_tag)
        result = client.get(key=new_tag.key)
        #add id, and self, and send data back to user
        result["id"] = str(new_tag.key.id)
        result["self"] = request.url_root + "tags/" + str(new_tag.key.id)
        print("New tag added:")
        print(result)
        #return created tag
        res = make_response(json.dumps(result))
        res.mimetype = 'application/json'
        res.status_code = 201
        return res


    elif request.method == 'GET':
        if 'application/json' != request.headers['Accept']:
            res = make_response(json.dumps(tag_errors["406"]))
            res.mimetype = 'application/json'
            res.status_code = 406
            return res

        query = client.query(kind=constants.tags)
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
            if "photos" in e.keys():
                for photo in e["photos"]:
                    photo["self"] = request.url_root + "photos/" + photo["id"]
            else:
                e["photos"] = []
            e["self"] = request.url_root + "tags/" + str(e.key.id)
        output = {"tags": results}
        if next_url:
            output["next"] = next_url

        query = client.query(kind=constants.tags)
        output["count"] = len(list(query.fetch()))
        res = make_response(json.dumps(output))
        res.mimetype = 'application/json'
        res.status_code = 200
        return res


    else:
        res = make_response(json.dumps(tag_errors["405"]))
        res.mimetype = 'application/json'
        res.status_code = 405
        return res


@bp.route('/<tag_id>', methods=['GET','DELETE', 'PATCH', 'PUT'])
def tag_get_delete_patch_put(tag_id):
    if request.method == 'GET':
        if 'application/json' != request.headers['Accept']:
            res = make_response(json.dumps(tag_errors["406"]))
            res.mimetype = 'application/json'
            res.status_code = 406
            return res
        tag = get_tag(tag_id)
        #tag_key = client.key(constants.tags, int(tag_id))
        #tag = client.get(key=tag_key)
        #if tag not found, return 404
        if tag == None:
            res = make_response(json.dumps(tag_errors["404"]))
            res.mimetype = 'application/json'
            res.status_code = 404
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
        res = make_response(json.dumps(tag))
        res.mimetype = 'application/json'
        res.status_code = 200
        return res


    elif request.method == 'PATCH':
        content = request.get_json()
        if request.content_type and 'application/json' not in request.content_type:
            res = make_response(json.dumps(tag_errors["415"]))
            res.mimetype = 'application/json'
            res.status_code = 415
            return res
        if 'application/json' != request.headers['Accept']:
            res = make_response(json.dumps(tag_errors["406"]))
            res.mimetype = 'application/json'
            res.status_code = 406
            return res
        if content == None:
            res = make_response(json.dumps(tag_errors["400_partial"]))
            res.mimetype = 'application/json'
            res.status_code = 400
            return res
        for field in content.keys():
            if field not in tag_attributes:
                res = make_response(json.dumps(tag_errors["400_partial"]))
                res.mimetype = 'application/json'
                res.status_code = 400
                return res
            if verify_tag(content[field], field) == False:
                res = make_response(json.dumps(tag_errors["400_partial"]))
                res.mimetype = 'application/json'
                res.status_code = 400
                return res
        if "name" in content:
            query = client.query(kind=constants.tags)
            results = list(query.fetch())
            for e in results:
                print(e)
                if e["name"].lower() == content["name"].lower() and e.key.id != tag_id:
                    res = make_response(json.dumps(tag_errors["409"]))
                    res.mimetype = 'application/json'
                    res.status_code = 409
                    return res
        tag = get_tag(tag_id, False)
        #if tag_id not found, return 404
        if tag == None:
            res = make_response(json.dumps(tag_errors["404"]))
            res.mimetype = 'application/json'
            res.status_code = 404
            return res
        for key in content.keys():
            tag[key] = content[key]
        client.put(tag)

        tag = get_tag(tag_id)

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
        res = make_response(json.dumps(tag))
        res.mimetype = 'application/json'
        res.status_code = 200
        return res


    elif request.method == 'PUT':
        content = request.get_json()
        if request.content_type and 'application/json' not in request.content_type:
            res = make_response(json.dumps(tag_errors["415"]))
            res.mimetype = 'application/json'
            res.status_code = 415
            return res
        if 'application/json' != request.headers['Accept']:
            res = make_response(json.dumps(tag_errors["406"]))
            res.mimetype = 'application/json'
            res.status_code = 406
            return res

        if content == None or len(content.keys()) != 3:
            res = make_response(json.dumps(tag_errors["400_required"]))
            res.mimetype = 'application/json'
            res.status_code = 400
            return res
        for field in content.keys():
            if field not in tag_attributes:
                res = make_response(json.dumps(tag_errors["400_required"]))
                res.mimetype = 'application/json'
                res.status_code = 400
                return res
            if verify_tag(content[field], field) == False:
                res = make_response(json.dumps(tag_errors["400_required"]))
                res.mimetype = 'application/json'
                res.status_code = 400
                return res

        query = client.query(kind=constants.tags)
        results = list(query.fetch())
        for e in results:
            if e["name"].lower() == content["name"].lower() and e.key.id != int(tag_id):
                print(e.key.id)
                print(tag_id)
                res = make_response(json.dumps(tag_errors["409"]))
                res.mimetype = 'application/json'
                res.status_code = 409
                return res
        tag = get_tag(int(tag_id), False)
        #if tag_id not found, return 404
        if tag == None:
            res = make_response(json.dumps(tag_errors["404"]))
            res.mimetype = 'application/json'
            res.status_code = 404
            return res
        for key in content.keys():
            tag[key] = content[key]
        client.put(tag)
        tag = get_tag(tag_id)

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
        res = make_response(json.dumps(tag))
        res.mimetype = 'application/json'
        res.status_code = 200
        return res

    elif request.method == 'DELETE':
        tag_key = client.key(constants.tags, int(tag_id))
        tag = client.get(key=tag_key)
        if tag == None:
            res = make_response(json.dumps(tag_errors["404"]))
            res.mimetype = 'application/json'
            res.status_code = 404
            return res
        if "photos" in tag.keys():
            for p in tag["photos"]:
                photo_key = client.key(constants.photos, int(p["id"]))
                photo = client.get(key=photo_key)
                for t in range(len(photo["tags"])):
                    if photo["tags"][t]["id"] == tag_id:
                        del photo["tags"][t]
                        break
                client.put(photo)
        client.delete(tag_key)
        return '',204
    else:
        res = make_response(json.dumps(tag_errors["405"]))
        res.mimetype = 'application/json'
        res.status_code = 405
        return res

def get_tag(tag_id, return_to_user= True):
    tag_key = client.key(constants.tags, int(tag_id))
    tag = client.get(key=tag_key)
    if tag == None:
        return None
    if return_to_user:
        #add id, self to data sent back to user
        tag["id"] = str(tag.key.id)
        tag["self"] = request.url_root + "tags/" + str(tag.key.id)
        if "photos" in tag.keys():
            for photo in tag["photos"]:
                photo["self"] = request.url_root + "photos/" + photo["id"]
        else:
            tag["photos"] = []
    return tag


def verify_tag(user_input, field):
    print(user_input)
    if not isinstance(user_input, str):
        print(isinstance)
        return False
    if field == "name":
        if 2 > len(user_input) or len(user_input) > 24:
            print("len")
            return False
        if user_input[0] != '#':
            print("hash")
            return False
        if is_accepted_characters(user_input) == False:
            print("char")
            return False
        print("nameOK")
    elif field == "description":
        if 1 > len(user_input) or len(user_input) > 256:
            return False
        if is_accepted_characters(user_input) == False:
            return False
        print("descriptionOK")
    elif field == "type":
        if user_input not in tag_types:
            return False
        print("typeOK")
    else:
        return True

def is_accepted_characters(input_string):
    return all(ord(c) >= 32 and ord(c)<=126 for c in input_string)
