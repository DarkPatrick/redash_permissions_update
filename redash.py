import requests
from dotenv import dotenv_values
import sqlite3
from tqdm import tqdm



SECRETS: dict = dotenv_values(".env")
 
REDASH_API_KEY: str = SECRETS.get("redash_api_key", "")
REDASH_BASE_URL: str = SECRETS.get("redash_base_url", "")
MY_GROUP_ID: int = SECRETS.get("my_redash_group_id", 0)


def send_request(
    url_suffix: str, 
    payload: dict | None = None, 
    get: bool=True
) -> dict | list | None:
    """send get or post request to redash api

    Args:
        url_suffix (str): api suffix: part of the url after /api/
        payload (dict | None, optional): payload for POST request. Defaults to None.
        get (bool, optional): whether to send a GET request. Defaults to True.

    Returns:
        dict | list | None: response from the API or None
        most of the requests will return dict. if there was an error that is recognised by redash,
        the response will contain "message" field with error description. In that case, None is returned.
        a few requsests will return list, e.g. getting users in group.
    """
    headers: dict = {
        'Authorization': f'Key {REDASH_API_KEY}',
        'Content-Type': 'application/json',
    }

    full_url: str = f"{REDASH_BASE_URL}/api/{url_suffix}"
    try:
        if get:
            response: requests.Response = requests.get(
                full_url,
                headers=headers
            )
        else:
            response: requests.Response = requests.post(
                full_url,
                headers=headers,
                json=payload
            )
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return None

    if response.status_code == 200:
        res: dict | list = response.json()
        if isinstance(res, dict) and res.get("message", "") != "":
            print("message:", res.get("message"))
            return None
        else:
            return res

    return None


def get_status() -> dict | None:
    """non api endpoint to get redash status info

    Returns:
        dict | None: basic info about memory usage, queries / dashboards count, etc.
    """
    headers: dict = {
        'Authorization': f'Key {REDASH_API_KEY}',
        'Content-Type': 'application/json',
    }
    full_url: str = f"{REDASH_BASE_URL}/status.json"
    try:
        response: requests.Response = requests.get(
            full_url,
            headers=headers
        )
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return None

    if response.status_code == 200:
        res: dict = response.json()
        if isinstance(res, dict) and res.get("message") is not None:
            print("message:", res.get("message"))
            return None
        else:
            return res
    else:
        print("response status code:", response.status_code)
    return None


def get_query_acl(query_id: int) -> dict | None:
    """get access control list for a query
    Args:
        query_id (int): query ID

    Returns:
        dict | list | None: users with access to modify the query 
        or None if request failed
    """
    url_suffix: str = f"queries/{query_id}/acl"
    data = send_request(url_suffix=url_suffix)
    if data is not None and not isinstance(data, dict):
        print("bad response format: ", type(data), "; expected dict")
        return None
    return data


def set_query_acl(
    query_id: int, 
    user_id: int, 
    owner_id: int | None = None
) -> None:
    """set access to modfy query by user

    Args:
        query_id (int): query ID
        user_id (int): user ID who will get access
        owner_id (int | None, optional): owner of query ID. Defaults to None.
    Returns:
        None
    """
    acl_payload: dict = {
        "access_type": "modify",
        "user_id": user_id
    }
    url_suffix: str = f"queries/{query_id}/acl"
    data = send_request(url_suffix=url_suffix, payload=acl_payload, get=False)
    if data is None:
        print(f"Failed to set ACL for query_id {query_id} and user_id {user_id}")
        return None
    try:
        conn: sqlite3.Connection = sqlite3.connect('queries.db')
        cursor: sqlite3.Cursor = conn.cursor()

        if owner_id is None:
            cursor.execute(
                "SELECT owner_id FROM queries WHERE query_id = ? LIMIT 1",
                (query_id,)
            )
            row = cursor.fetchone()
            if row is not None and row[0] is not None:
                try:
                    owner_id = int(row[0])
                except (TypeError, ValueError):
                    owner_id = None

        if owner_id is None:
            print(f"owner_id not provided and not found for query_id {query_id}; skipping DB insert")
        else:
            cursor.execute('''
                INSERT OR IGNORE INTO queries (query_id, owner_id, editor_id)
                VALUES (?, ?, ?)
            ''', (query_id, owner_id, user_id))
            conn.commit()
    except sqlite3.Error as e:
        print(f"DB error: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return None


def get_queries(page: int=1, page_size: int=25) -> dict | None:
    """get redash queries

    Args:
        page (int, optional): number of page to load.
        newest queries are on first page.
        Defaults to 1.
        page_size (int, optional): number of queries per page. Defaults to 25.

    Returns:
        dict | None: dictionary with full info of queries or None if request failed
    """
    url_suffix: str = f"queries?page_size={page_size}&page={page}"
    data = send_request(url_suffix=url_suffix)
    if data is not None and not isinstance(data, dict):
        print("bad response format: ", type(data), "; expected dict")
        return None
    return data


def get_users_in_group(group_id: int) -> list | None:
    """get members of the group

    Args:
        group_id (int): group ID

    Returns:
        list | None: list of users in the group or None if request failed
    """
    url_suffix: str = f"groups/{group_id}/members"
    data = send_request(url_suffix=url_suffix)
    if data is not None and not isinstance(data, list):
        print("bad response format: ", type(data), "; expected list")
        return None
    return data


def get_user_info(user_id: int) -> dict | None:
    """get info about user

    Args:
        user_id (int): user ID

    Returns:
        dict | None: dict with user info or None if request failed
    """
    url_suffix: str = f"users/{user_id}"
    data = send_request(url_suffix=url_suffix)
    if data is not None and not isinstance(data, dict):
        print("bad response format: ", type(data), "; expected dict")
        return None
    return data


def download_queries_info() -> None:
    """dowload all existing queries to local sqlite db "queries"
    Returns:
        None
    """
    conn: sqlite3.Connection = sqlite3.connect('queries.db')
    cursor: sqlite3.Cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS queries (
            query_id INTEGER,
            owner_id INTEGER,
            editor_id INTEGER,
            PRIMARY KEY (query_id, owner_id, editor_id)  -- non-unique primary key
        )
    ''')

    conn.commit()

    status: dict | None = get_status()
    if status is None or not isinstance(status, dict):
        return None
    page_size: int = 25
    pages: int = int(status.get("queries_count", 1)) // page_size + 1
    
    for page in tqdm(range(pages)):
        queries_info = get_queries(page=page + 1, page_size=25)
        if queries_info is None or not isinstance(queries_info, dict):
            break
        queries = queries_info.get("results")
        if not isinstance(queries, list):
            break

        has_new_query: int = 0
        for query in queries:
            if (not isinstance(query, dict) or query.get("user") is None 
                or not isinstance(query.get("user"), dict)):
                continue
            pass
            query_id: int = int(query.get("id", 0))
            user: dict = query.get("user", {})
            owner_id: int = int(user.get("id", 0))
            editor_id: int = owner_id
            
            cursor.execute(
                "SELECT editor_id FROM queries WHERE query_id = ? AND owner_id = ?",
                (query_id, owner_id)
            )
            existing = cursor.fetchone()
            if existing is None:
                has_new_query = 1
                # print(query_id, owner_id, editor_id)
                cursor.execute('''
                    INSERT OR IGNORE INTO queries (query_id, owner_id, editor_id)
                    VALUES (?, ?, ?)
                ''', (query_id, owner_id, editor_id))
                conn.commit()
        if has_new_query == 0:
            print("no new rows found. exiting...")
            break

    conn.close()
    return None


def get_user_queries(user_id: int) -> list[int]:
    """find all queries in queries.db that belong to exact user

    Args:
        user_id (int): user ID

    Returns:
        list[int]: list of queries IDs belonging to the user
    """
    conn: sqlite3.Connection = sqlite3.connect('queries.db')
    cursor: sqlite3.Cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT query_id FROM queries WHERE owner_id = ?",
            (user_id,)
        )
        rows: list = cursor.fetchall()
    except sqlite3.Error as e:
        print(f"DB error: {e}")
        conn.close()
        return []

    conn.close()

    query_ids: list[int] = []
    for row in rows:
        try:
            query_ids.append(int(row[0]))
        except (TypeError, ValueError):
            continue

    seen: set[int] = set()
    result: list[int] = []
    for q in query_ids:
        if q not in seen:
            seen.add(q)
            result.append(q)

    return result


def get_user_queries_with_editors(user_id: int) -> dict[int, list[int]]:
    """find all queries in queries.db that belong to exact user
    along with all editors who have access to each query

    Args:
        user_id (int): user ID

    Returns:
        dict[int, list[int]]: dictionary where keys are query IDs
        and values are lists of editor IDs who have access to the query
    """
    conn: sqlite3.Connection = sqlite3.connect('queries.db')
    cursor: sqlite3.Cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT query_id, GROUP_CONCAT(editor_id) FROM queries WHERE owner_id = ? GROUP BY query_id",
            (user_id,)
        )
        rows: list = cursor.fetchall()
    except sqlite3.Error as e:
        print(f"DB error: {e}")
        conn.close()
        return {}

    conn.close()

    query_editors: dict[int, list[int]] = {}
    print(rows)
    for row in rows:
        try:
            query_id: int = int(row[0])
            editor_id: int = int(row[1])
        except (TypeError, ValueError):
            continue

        if query_id not in query_editors:
            query_editors[query_id] = []
        query_editors[query_id].append(editor_id)

    return query_editors


def has_access(query_id: int, user_id: int) -> int:
    """check if there is a record in queries.db that user has access to a query

    Args:
        query_id (int): query ID
        user_id (int): user ID
    Returns:
        int: 1 if user has access, 0 otherwise
    """
    conn: sqlite3.Connection = sqlite3.connect('queries.db')
    cursor: sqlite3.Cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT 1 FROM queries WHERE query_id = ? AND editor_id = ? LIMIT 1",
            (query_id, user_id)
        )
        row = cursor.fetchone()
    except sqlite3.Error as e:
        print(f"DB error: {e}")
        conn.close()
        return 0
    conn.close()
    return 1 if row is not None else 0


def update_accesses_in_group(group_id: int) -> None:
    """update rights to all queries for all users in the group to each other
    for example: if user A and user B are in the same group,
    and user A is the owner of query Q, then user B will get access to it
    along with all the other queries owned by user A
    and same for all users in the group
    Args:
        group_id (int): group ID

    Returns:
        None
    """
    group_members = get_users_in_group(group_id)
    if group_members is None or not isinstance(group_members, list):
        print("No group members found or invalid data")
        return None

    users: list[int] = []
    for member in group_members:
        if not isinstance(member, dict) or member.get("id", 0) == 0:
            continue
        users.append(member.get("id", 0))

    for user in tqdm(users):
        member_queries: list[int] = get_user_queries(user)
        for editor in tqdm(users, leave=False):
            if editor == user:
                continue
            for query in tqdm(member_queries, leave=False):
                if has_access(query, editor) == 0:
                    set_query_acl(query, editor, user)

    return None



if __name__ == "__main__":
    # downloads all existing queries to local sqlite db "queries"
    download_queries_info()
    # updates accesses in queries for all users in the group to each other
    update_accesses_in_group(MY_GROUP_ID) #ug monetization
    update_accesses_in_group(7) # UG data analysts
