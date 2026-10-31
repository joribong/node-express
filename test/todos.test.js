const { describe, it, before, after, beforeEach } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');

process.env.NODE_ENV = 'test';
process.env.DB_PATH = ':memory:';
const app = require('../app');
const store = require('../models/todoStore');

let server;
let baseUrl;

before(async () => {
  server = http.createServer(app);
  await new Promise((resolve) => server.listen(0, resolve));
  baseUrl = `http://127.0.0.1:${server.address().port}/api/todos`;
});

after(() => new Promise((resolve) => server.close(resolve)));

beforeEach(() => store.reset());

function request(path, { method = 'GET', body, rawBody } = {}) {
  const options = { method, headers: {} };
  if (body !== undefined || rawBody !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = rawBody !== undefined ? rawBody : JSON.stringify(body);
  }
  return fetch(baseUrl + path, options);
}

async function createTodo(title, completed) {
  const res = await request('', { method: 'POST', body: { title, completed } });
  return res.json();
}

describe('POST /api/todos', () => {
  it('creates a todo', async () => {
    const res = await request('', { method: 'POST', body: { title: '  우유 사기  ' } });
    assert.equal(res.status, 201);
    assert.equal(res.headers.get('location'), '/api/todos/1');
    const todo = await res.json();
    assert.equal(todo.id, 1);
    assert.equal(todo.title, '우유 사기');
    assert.equal(todo.completed, false);
    assert.ok(todo.createdAt);
    assert.equal(todo.createdAt, todo.updatedAt);
  });

  it('rejects a missing title', async () => {
    const res = await request('', { method: 'POST', body: {} });
    assert.equal(res.status, 400);
    const body = await res.json();
    assert.deepEqual(body.error.details, ['"title" is required']);
  });

  it('rejects invalid field types', async () => {
    const res = await request('', { method: 'POST', body: { title: '   ', completed: 'yes' } });
    assert.equal(res.status, 400);
    const body = await res.json();
    assert.equal(body.error.details.length, 2);
  });

  it('rejects a title that is too long', async () => {
    const res = await request('', { method: 'POST', body: { title: 'a'.repeat(201) } });
    assert.equal(res.status, 400);
  });

  it('rejects a request without a JSON body', async () => {
    // In Express 5, req.body is undefined when no body parser matched.
    const res = await fetch(baseUrl, { method: 'POST' });
    assert.equal(res.status, 400);
    const body = await res.json();
    assert.deepEqual(body.error.details, ['Request body must be a JSON object']);
  });

  it('returns a JSON error for malformed JSON', async () => {
    const res = await request('', { method: 'POST', rawBody: '{bad json' });
    assert.equal(res.status, 400);
    const body = await res.json();
    assert.equal(body.error.status, 400);
  });
});

describe('GET /api/todos', () => {
  it('returns an empty list initially', async () => {
    const res = await request('');
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), []);
  });

  it('lists and filters by completed', async () => {
    await createTodo('a', false);
    await createTodo('b', true);

    assert.equal((await (await request('')).json()).length, 2);

    const done = await (await request('?completed=true')).json();
    assert.deepEqual(done.map((t) => t.title), ['b']);

    const open = await (await request('?completed=false')).json();
    assert.deepEqual(open.map((t) => t.title), ['a']);
  });

  it('rejects an invalid completed filter', async () => {
    const res = await request('?completed=maybe');
    assert.equal(res.status, 400);
  });
});

describe('GET /api/todos/:id', () => {
  it('returns a todo', async () => {
    const created = await createTodo('a');
    const res = await request(`/${created.id}`);
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), created);
  });

  it('returns 404 for an unknown id', async () => {
    const res = await request('/999');
    assert.equal(res.status, 404);
    const body = await res.json();
    assert.equal(body.error.message, 'Todo not found');
  });

  it('returns 400 for an invalid id', async () => {
    assert.equal((await request('/abc')).status, 400);
    assert.equal((await request('/0')).status, 400);
    assert.equal((await request('/1.5')).status, 400);
  });
});

describe('PUT /api/todos/:id', () => {
  it('replaces a todo', async () => {
    const created = await createTodo('a');
    const res = await request(`/${created.id}`, {
      method: 'PUT',
      body: { title: 'b', completed: true },
    });
    assert.equal(res.status, 200);
    const todo = await res.json();
    assert.equal(todo.title, 'b');
    assert.equal(todo.completed, true);
    assert.equal(todo.createdAt, created.createdAt);
  });

  it('requires both fields', async () => {
    const created = await createTodo('a');
    const res = await request(`/${created.id}`, { method: 'PUT', body: { title: 'b' } });
    assert.equal(res.status, 400);
  });

  it('returns 404 for an unknown id', async () => {
    const res = await request('/999', { method: 'PUT', body: { title: 'b', completed: true } });
    assert.equal(res.status, 404);
  });
});

describe('PATCH /api/todos/:id', () => {
  it('updates only the given fields', async () => {
    const created = await createTodo('a');
    const res = await request(`/${created.id}`, { method: 'PATCH', body: { completed: true } });
    assert.equal(res.status, 200);
    const todo = await res.json();
    assert.equal(todo.title, 'a');
    assert.equal(todo.completed, true);
  });

  it('rejects an empty body', async () => {
    const created = await createTodo('a');
    const res = await request(`/${created.id}`, { method: 'PATCH', body: {} });
    assert.equal(res.status, 400);
  });

  it('returns 404 for an unknown id', async () => {
    const res = await request('/999', { method: 'PATCH', body: { completed: true } });
    assert.equal(res.status, 404);
  });
});

describe('DELETE /api/todos/:id', () => {
  it('deletes a todo', async () => {
    const created = await createTodo('a');
    const res = await request(`/${created.id}`, { method: 'DELETE' });
    assert.equal(res.status, 204);
    assert.equal((await request(`/${created.id}`)).status, 404);
  });

  it('returns 404 for an unknown id', async () => {
    const res = await request('/999', { method: 'DELETE' });
    assert.equal(res.status, 404);
  });
});

describe('non-API routes', () => {
  it('still render HTML error pages', async () => {
    const res = await fetch(baseUrl.replace('/api/todos', '/no-such-page'));
    assert.equal(res.status, 404);
    assert.match(res.headers.get('content-type'), /text\/html/);
  });
});
