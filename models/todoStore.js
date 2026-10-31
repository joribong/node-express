/**
 * In-memory Todo store.
 * Data lives only for the lifetime of the process (it is lost on restart).
 */

let todos = [];
let nextId = 1;

function list(filter = {}) {
  if (typeof filter.completed === 'boolean') {
    return todos.filter((todo) => todo.completed === filter.completed);
  }
  return todos.slice();
}

function get(id) {
  return todos.find((todo) => todo.id === id) || null;
}

function create({ title, completed = false }) {
  const now = new Date().toISOString();
  const todo = { id: nextId++, title, completed, createdAt: now, updatedAt: now };
  todos.push(todo);
  return todo;
}

function update(id, changes) {
  const todo = get(id);
  if (!todo) return null;
  if (changes.title !== undefined) todo.title = changes.title;
  if (changes.completed !== undefined) todo.completed = changes.completed;
  todo.updatedAt = new Date().toISOString();
  return todo;
}

function remove(id) {
  const index = todos.findIndex((todo) => todo.id === id);
  if (index === -1) return false;
  todos.splice(index, 1);
  return true;
}

// Used by tests to start from a clean state.
function reset() {
  todos = [];
  nextId = 1;
}

module.exports = { list, get, create, update, remove, reset };
