import time
import requests
from dotenv import dotenv_values
import os
import json


secrets: dict = dotenv_values(".env")
 
REDASH_API_KEY = secrets["redash_api_key"]
REDASH_BASE_URL = secrets["redash_base_url"]

def send_request(url_suffix, payload=None, get=True):
    headers = {
        'Authorization': f'Key {REDASH_API_KEY}',
        'Content-Type': 'application/json',
    }

    full_url = f"{REDASH_BASE_URL}/api/{url_suffix}"
    if get:
        response = requests.get(
            full_url,
            headers=headers
        )
    else:
        response = requests.post(
            full_url,
            headers=headers,
            json=payload
        )

    res = response.json()
    return res


def get_query_acl(query_id):
    url_suffix = f"queries/{query_id}/acl"
    data = send_request(url_suffix=url_suffix)
    return data


def set_query_acl(query_id, user_id):
    acl_payload = {
        "access_type": "modify",
        "user_id": user_id
    }
    url_suffix = f"queries/{query_id}/acl"
    data = send_request(url_suffix=url_suffix, payload=acl_payload, get=False)
    # if not error in response then add info in local file with format: query_id, user_ids
    # append to file query_acl_updates_log.json: format {query_id: [user_id1, user_id2, ...]}
    log_path = os.path.join(os.path.dirname(__file__), "query_acl_updates_log.json")

    # Only write to log if response contains no error fields
    if not (isinstance(data, dict) and (data.get("error") or data.get("errors"))):
        try:
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    log = json.load(f)
            else:
                log = {}
        except (json.JSONDecodeError, IOError):
            log = {}

        key = str(query_id)
        users = log.get(key, [])
        if user_id not in users:
            users.append(user_id)
            log[key] = users
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(log, f, indent=2)
    return data


def get_users_in_group(group_id):
    url_suffix = f"groups/{group_id}/members"
    data = send_request(url_suffix=url_suffix)
    return data


def get_user_info(user_id):
    url_suffix = f"users/{user_id}"
    data = send_request(url_suffix=url_suffix)
    return data




if __name__ == "__main__":
    # check that connection is working correctly
    # insert here any valid query id preferably one that multiple people have access to
    # data = get_query_acl(21956)
    # print("QUERY ACL:")
    # print(data)
    
    # data = get_user_info(user_id=23)
    # print("USER INFO:")
    # print(data["id"])

    # data = get_users_in_group(group_id=6)
    # print("USERS IN GROUP:")
    # print(data)
    
    
    data = get_query_acl(21955)
    print("QUERY ACL:")
    print(data)
    data=set_query_acl(query_id=21955, user_id=375)
    print("SET QUERY ACL RESPONSE:")
    print(data)
    data = get_query_acl(21955)
    print("QUERY ACL:")
    print(data)
