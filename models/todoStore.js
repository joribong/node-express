/**
 * Todo store backed by SQLite (see db/index.js).
 */
const db = require('../db');

const statements = {
  listAll: db.prepare('SELECT * FROM todos ORDER BY id'),
  listByCompleted: db.prepare('SELECT * FROM todos WHERE completed = ? ORDER BY id'),
  get: db.prepare('SELECT * FROM todos WHERE id = ?'),
  insert: db.prepare(
    'INSERT INTO todos (title, completed, created_at, updated_at) VALUES (?, ?, ?, ?)'
  ),
  update: db.prepare(
    'UPDATE todos SET title = ?, completed = ?, updated_at = ? WHERE id = ?'
  ),
  remove: db.prepare('DELETE FROM todos WHERE id = ?'),
};

// Convert a database row into the API shape.
function toTodo(row) {
  if (!row) return null;
  return {
    id: row.id,
    title: row.title,
    completed: row.completed === 1,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

function list(filter = {}) {
  const rows =
    typeof filter.completed === 'boolean'
      ? statements.listByCompleted.all(filter.completed ? 1 : 0)
      : statements.listAll.all();
  return rows.map(toTodo);
}

function get(id) {
  return toTodo(statements.get.get(id));
}

function create({ title, completed = false }) {
  const now = new Date().toISOString();
  const result = statements.insert.run(title, completed ? 1 : 0, now, now);
  return get(Number(result.lastInsertRowid));
}

const update = db.transaction((id, changes) => {
  const todo = get(id);
  if (!todo) return null;
  const title = changes.title !== undefined ? changes.title : todo.title;
  const completed = changes.completed !== undefined ? changes.completed : todo.completed;
  statements.update.run(title, completed ? 1 : 0, new Date().toISOString(), id);
  return get(id);
});

function remove(id) {
  return statements.remove.run(id).changes > 0;
}

// Delete all todos and restart ids from 1. Used by tests.
const reset = db.transaction(() => {
  db.exec('DELETE FROM todos');
  db.exec("DELETE FROM sqlite_sequence WHERE name = 'todos'");
});

module.exports = { list, get, create, update, remove, reset };
