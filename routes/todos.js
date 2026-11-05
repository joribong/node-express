const express = require('express');
const createError = require('http-errors');
const store = require('../models/todoStore');

const router = express.Router();

const TITLE_MAX_LENGTH = 200;

/**
 * Validate a request body.
 * @param {object} body
 * @param {{ requireTitle: boolean, requireCompleted: boolean }} options
 * @returns {{ errors: string[], value: object }}
 */
function validate(body, { requireTitle, requireCompleted }) {
  const errors = [];
  const value = {};

  if (body === null || typeof body !== 'object' || Array.isArray(body)) {
    return { errors: ['Request body must be a JSON object'], value };
  }

  if (body.title === undefined) {
    if (requireTitle) errors.push('"title" is required');
  } else if (typeof body.title !== 'string' || body.title.trim() === '') {
    errors.push('"title" must be a non-empty string');
  } else if (body.title.trim().length > TITLE_MAX_LENGTH) {
    errors.push(`"title" must be at most ${TITLE_MAX_LENGTH} characters`);
  } else {
    value.title = body.title.trim();
  }

  if (body.completed === undefined) {
    if (requireCompleted) errors.push('"completed" is required');
  } else if (typeof body.completed !== 'boolean') {
    errors.push('"completed" must be a boolean');
  } else {
    value.completed = body.completed;
  }

  return { errors, value };
}

function parseId(req, res, next, raw) {
  const id = Number(raw);
  if (!Number.isInteger(id) || id < 1) {
    return next(createError(400, 'Invalid todo id'));
  }
  req.todoId = id;
  next();
}

router.param('id', parseId);

/* GET /api/todos?completed=true|false — list todos */
router.get('/', (req, res, next) => {
  const filter = {};
  const { completed } = req.query;
  if (completed !== undefined) {
    if (completed !== 'true' && completed !== 'false') {
      return next(createError(400, '"completed" query must be "true" or "false"'));
    }
    filter.completed = completed === 'true';
  }
  res.json(store.list(filter));
});

/* GET /api/todos/:id — get one todo */
router.get('/:id', (req, res, next) => {
  const todo = store.get(req.todoId);
  if (!todo) return next(createError(404, 'Todo not found'));
  res.json(todo);
});

/* POST /api/todos — create a todo */
router.post('/', (req, res, next) => {
  const { errors, value } = validate(req.body, { requireTitle: true, requireCompleted: false });
  if (errors.length) return next(createError(400, 'Validation failed', { details: errors }));
  const todo = store.create(value);
  res.status(201).location(`${req.baseUrl}/${todo.id}`).json(todo);
});

/* PUT /api/todos/:id — replace a todo (title and completed required) */
router.put('/:id', (req, res, next) => {
  const { errors, value } = validate(req.body, { requireTitle: true, requireCompleted: true });
  if (errors.length) return next(createError(400, 'Validation failed', { details: errors }));
  const todo = store.update(req.todoId, value);
  if (!todo) return next(createError(404, 'Todo not found'));
  res.json(todo);
});

/* PATCH /api/todos/:id — partially update a todo */
router.patch('/:id', (req, res, next) => {
  const { errors, value } = validate(req.body, { requireTitle: false, requireCompleted: false });
  if (!errors.length && Object.keys(value).length === 0) {
    errors.push('Provide at least one of "title" or "completed"');
  }
  if (errors.length) return next(createError(400, 'Validation failed', { details: errors }));
  const todo = store.update(req.todoId, value);
  if (!todo) return next(createError(404, 'Todo not found'));
  res.json(todo);
});

/* DELETE /api/todos/:id — delete a todo */
router.delete('/:id', (req, res, next) => {
  if (!store.remove(req.todoId)) return next(createError(404, 'Todo not found'));
  res.status(204).end();
});

module.exports = router;
