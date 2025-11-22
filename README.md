# Redash Group Query Sharing Helper

This repository contains a small Python utility script, `redash.py`, that talks to the [Redash](https://redash.io) API.

Its main purpose:

1. Download metadata about all existing queries in your Redash instance into a local SQLite database (`queries.db`).
2. For a given Redash group, automatically grant **modify** access to **all queries owned by any user in the group** to **all other users in the same group**.

In other words: if Alice and Bob are in the same Redash group, and Alice owns query Q, this script will grant Bob modify access to Q as well (and vice versa).

---

## Features Overview

The `redash.py` module provides several helper functions:

- **Low-level helpers**
  - `send_request(...)` – wrapper around GET/POST requests to the Redash API.
  - `get_status()` – fetches `/status.json` (non-API endpoint) with global instance info (includes `queries_count`).
  - `get_queries(page, page_size)` – loads queries via `/api/queries`.

- **Access control**
  - `get_query_acl(query_id)` – get ACL (Access Control List) for a specific query.
  - `set_query_acl(query_id, user_id, owner_id=None)` – grant *modify* rights on a query to a user and store this fact in `queries.db`.
  - `get_users_in_group(group_id)` – list all users in a Redash group.
  - `get_user_info(user_id)` – fetch basic info about a user.

- **Local SQLite database (`queries.db`)**
  - `download_queries_info()` – downloads all queries and writes them to `queries.db`:
    - Table: `queries(query_id, owner_id, editor_id)`
    - For each query, it stores at least one row where `editor_id == owner_id` (the owner can edit).
    - Skips already known combinations to avoid duplicates.
  - `get_user_queries(user_id)` – returns a list of query IDs owned by the specified user (from `queries.db`).
  - `has_access(query_id, user_id)` – checks if a user already has recorded edit access to a query.

- **Group-wide sharing**
  - `update_accesses_in_group(group_id)` – for all users in the given group:
    - For each “owner” user, gets all their queries from `queries.db`.
    - For each other user in that group, if they do **not** yet have access to a query, the script:
      1. Calls `set_query_acl` to grant `modify` rights in Redash.
      2. Records that (query, owner, editor) pairing in `queries.db`.

---

## Environment Configuration (.env)

The script expects a `.env` file in the same directory where you run it.  
These variables are read using `python-dotenv` (`dotenv_values(".env")`):

```env
redash_api_key=YOUR_REDASH_API_KEY_HERE
redash_base_url=https://redash.example.com
my_redash_group_id=123
```

- `redash_api_key`
  - Your Redash user API key (must have enough permissions to read queries and manage ACLs).
- `redash_base_url`
  - Base URL of your Redash instance **without** trailing slash.
  - Example: `https://redash.company.internal`
- `my_redash_group_id`
  - Integer ID of the Redash group whose members should share queries with each other.

> ⚠️ Make sure your API key belongs to a user who:
> - Can read all desired queries.
> - Has permission to edit their ACL (e.g., admin or query owner with elevated rights).

---

## Installation & Setup (with `venv`)

Below is a typical installation scenario using Python’s built-in virtual environment (`venv`).

### 1. Clone / copy the project

```bash
git clone <your-repo-url>.git
cd <your-repo-folder>
```

Make sure `redash.py` and `requirements.txt` are in this folder.

### 2. Create and activate a virtual environment

**On macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**On Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` should at least include:

- `requests`
- `python-dotenv`
- `tqdm`

(And any other libraries your project uses.)

### 4. Create your `.env` file

In the project root (same folder as `redash.py`):

```bash
cp .env.example .env  # if you have an example
# OR create manually:
nano .env  # or any text editor
```

Fill it as described above:

```env
redash_api_key=YOUR_REDASH_API_KEY_HERE
redash_base_url=https://redash.example.com
my_redash_group_id=123
```

---

## How the Script Works When Run Directly

At the bottom of `redash.py` you have:

```python
if __name__ == "__main__":
    # downloads all existing queries to local sqlite db "queries"
    download_queries_info()
    # updates accesses in queries for all users in the group to each other
    update_accesses_in_group(MY_GROUP_ID)
```

So when you run:

```bash
python redash.py
```

it will:

1. **Download queries metadata** from Redash and store it in `queries.db`.
   - Uses `get_status()` to know how many queries exist.
   - Iterates through all pages with `get_queries(page=..., page_size=25)`.
   - For each query:
     - Extracts `id` ➜ `query_id`.
     - Extracts owner user ID from `query["user"]["id"]` ➜ `owner_id`.
     - Inserts row `(query_id, owner_id, editor_id=owner_id)` into SQLite (if not already present).
   - Stops when a page doesn’t introduce any new queries.

2. **Update group-wide access** to those queries via `update_accesses_in_group(MY_GROUP_ID)`:
   - Reads users in the Redash group `MY_GROUP_ID` via `/api/groups/{id}/members`.
   - For each group member (as an owner):
     - Finds all queries they own via `get_user_queries(owner_id)` from `queries.db`.
     - For each other member in the group:
       - If `has_access(query_id, other_user_id)` returns `0` (no access recorded):
         - Calls `set_query_acl(query_id, other_user_id, owner_id)` which:
           - Sends a POST to `/api/queries/{query_id}/acl` with `{"access_type": "modify", "user_id": other_user_id}`.
           - On success, inserts `(query_id, owner_id, editor_id=other_user_id)` into the database.

Result: every member of the group gains modify access to every query owned by any other member in that group.

---

## Usage Examples

### Example 1: Run the script once to sync everything

From your activated virtual environment:

```bash
python redash.py
```

Typical use case: set up a cron job to run this periodically (e.g., once per night) to keep group access in sync.

### Example 2: Use functions programmatically

You can also import `redash.py` into another Python script or an interactive shell:

```python
from redash import (
    download_queries_info,
    update_accesses_in_group,
    get_users_in_group,
    get_user_queries,
    set_query_acl,
)

# 1. Refresh local query database
download_queries_info()

# 2. Update all access rights within group 123
update_accesses_in_group(123)

# 3. Inspect which users are in a group
members = get_users_in_group(123)
print(members)

# 4. Get all query IDs owned by a specific user
alice_id = 42
alice_queries = get_user_queries(alice_id)
print("Alice's queries:", alice_queries)

# 5. Manually grant user 99 modify access to query 555
set_query_acl(query_id=555, user_id=99)
```

### Example 3: Inspect the local SQLite database

After running `download_queries_info()`, you can look into `queries.db` with the `sqlite3` CLI:

```bash
sqlite3 queries.db
```

Then in the SQLite prompt:

```sql
.tables;
.schema queries;
SELECT * FROM queries LIMIT 10;
```

You should see rows like:

```text
query_id | owner_id | editor_id
--------------------------------
1001     |    7     |     7
1002     |    8     |     8
1001     |    7     |     9  -- user 9 also got access to query 1001
...
```

---

## Error Handling & Logging Notes

- **HTTP errors / network issues**  
  Most API calls are wrapped in `try/except` blocks:
  - If a `requests.RequestException` occurs, the script prints `Request failed: <error>` and returns `None`.
- **Redash API “message” field**  
  If the API returns JSON with a `message` key (for example, permission issues or incorrect payload), the helper functions print that message and treat it as a failure (`None`).
- **Database errors**  
  All SQLite access is also wrapped in `try/except sqlite3.Error`, printing `DB error: <error>` and failing gracefully.

---

## Requirements & Compatibility

- Python **3.10+** (because of the `dict | None` type-hint syntax).
- Redash with API access enabled.
- An API key with enough permissions to:
  - Read queries.
  - Read users and groups.
  - Modify query ACLs.

Install Python packages via:

```bash
pip install -r requirements.txt
```

If you encounter issues:

- Double-check your `.env` values.
- Ensure your `redash_base_url` is reachable from the environment where you run this script.
- Confirm that the API key belongs to a user with rights to manage the ACLs of the queries you want to share.

---

## Typical Workflow Summary

1. Configure `.env` with your Redash endpoint, API key, and group ID.
2. Create and activate a virtual environment.
3. Install dependencies from `requirements.txt`.
4. Run `python redash.py`:
   - Builds/updates `queries.db`.
   - Synchronizes query access for everyone in the chosen group.
5. Optionally, import functions from `redash.py` into your own tools and automation scripts.

You can now maintain group-wide, symmetric access to Redash queries with a single script.
