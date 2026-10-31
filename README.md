# example-node-express



## Install

```
$ npm i
```

## Running

```
npm start
```

## Test

```
npm test
```

## Todo REST API

Base URL: `/api/todos` (JSON).

## Database

Todos are stored in SQLite via [better-sqlite3](https://github.com/WiseLibs/better-sqlite3).
No separate database server is needed; the table is created automatically on startup.

| Env var | Default | Description |
|---|---|---|
| `DB_PATH` | `data/app.db` | SQLite file path (`:memory:` for an in-memory DB). The `data/` folder is git-ignored. |

```
DB_PATH=/var/lib/myapp/app.db npm start
```

Tests run against an in-memory database, so they never touch your data file.

| Method | Path | Description | Success |
|---|---|---|---|
| GET | `/api/todos` | List todos (optional `?completed=true\|false`) | 200 |
| GET | `/api/todos/:id` | Get one todo | 200 |
| POST | `/api/todos` | Create (`title` required, `completed` optional) | 201 |
| PUT | `/api/todos/:id` | Replace (`title` and `completed` required) | 200 |
| PATCH | `/api/todos/:id` | Partial update (`title` and/or `completed`) | 200 |
| DELETE | `/api/todos/:id` | Delete | 204 |

Todo shape:

```json
{ "id": 1, "title": "Buy milk", "completed": false, "createdAt": "...", "updatedAt": "..." }
```

Errors are returned as JSON (400 for validation errors / bad id / malformed JSON, 404 when not found):

```json
{ "error": { "status": 400, "message": "Validation failed", "details": ["\"title\" is required"] } }
```

Example:

```
curl -X POST localhost:3000/api/todos -H 'Content-Type: application/json' -d '{"title":"Buy milk"}'
curl -X PATCH localhost:3000/api/todos/1 -H 'Content-Type: application/json' -d '{"completed":true}'
curl localhost:3000/api/todos?completed=true
curl -X DELETE localhost:3000/api/todos/1
```
