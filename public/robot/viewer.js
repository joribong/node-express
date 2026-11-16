import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const $ = (id) => document.getElementById(id);
const el = (tag, text, cls) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
};

// ------------------------------------------------------------ 3D 화면
const viewport = $('viewport');
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
viewport.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xe2e8f0);
scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 1.6));
const sun = new THREE.DirectionalLight(0xffffff, 2.0);
sun.position.set(1, 2, 1.5);
scene.add(sun);

const camera = new THREE.PerspectiveCamera(35, 1, 0.001, 100);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

let current = null;        // 지금 보이는 모델
let homeView = null;

function resize() {
  const w = viewport.clientWidth, h = viewport.clientHeight;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(viewport);

function frameModel(object) {
  const box = new THREE.Box3().setFromObject(object);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const radius = size.length() / 2;
  const dist = radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2)) * 1.05;
  camera.near = dist / 100;
  camera.far = dist * 100;
  camera.updateProjectionMatrix();
  camera.position.copy(center).add(new THREE.Vector3(0.75, 0.6, 0.9).normalize().multiplyScalar(dist));
  controls.target.copy(center);
  controls.update();
  homeView = { position: camera.position.clone(), target: center.clone() };
}

// 부품 이름은 "종류_번호" 형식 (예: motor_3). 같은 이름이 여러 번 나오면
// 불러올 때 뒤에 번호가 더 붙으므로(motor_3_1) 앞부분의 종류만 꺼낸다.
const KIND = /^(body|lid|wheel|motor|cell|pcb|magnet|pogo|pad|latch|servo)_\d+/;
const kindOf = (mesh) => {
  for (let node = mesh; node; node = node.parent) {
    const found = KIND.exec(node.name || '');
    if (found) return found[1];
  }
  return '';
};

function applyDisplayOptions() {
  if (!current) return;
  const showLid = $('showLid').checked, ghost = $('ghostBody').checked;
  current.traverse((o) => {
    if (!o.isMesh) return;
    const kind = o.userData.kind;
    if (kind === 'lid') o.visible = showLid;
    if (kind === 'body') {
      o.material.transparent = ghost;
      o.material.opacity = ghost ? 0.25 : 1;
      o.material.depthWrite = !ghost;
    }
  });
}

function highlight(kind) {
  if (!current) return;
  current.traverse((o) => {
    if (!o.isMesh) return;
    const on = kind && o.userData.kind === kind;
    o.material.emissive.setHex(on ? 0xff7a00 : 0x000000);
    o.material.emissiveIntensity = on ? 0.9 : 0;
  });
}

const loader = new GLTFLoader();
function loadModel(url) {
  $('status').textContent = '3D 형상을 불러오는 중…';
  return new Promise((resolve, reject) => {
    loader.load(url, (gltf) => {
      if (current) scene.remove(current);
      current = gltf.scene;
      current.traverse((o) => {
        if (!o.isMesh) return;
        o.material = o.material.clone();      // 부품마다 따로 강조할 수 있게
        o.material.side = THREE.DoubleSide;
        o.userData.kind = kindOf(o);
      });
      scene.add(current);
      applyDisplayOptions();
      frameModel(current);
      $('status').textContent = '';
      resolve();
    }, undefined, (err) => {
      $('status').textContent = '3D 파일을 불러오지 못했습니다.';
      reject(err);
    });
  });
}

renderer.setAnimationLoop(() => {
  controls.update();
  renderer.render(scene, camera);
});

// ------------------------------------------------------------ 표와 양식
function fillTable(table, head, rows) {
  table.replaceChildren();
  const thead = el('thead'), tr = el('tr');
  head.forEach((h) => tr.appendChild(el('th', h.text, h.num ? 'num' : '')));
  thead.appendChild(tr);
  const tbody = el('tbody');
  rows.forEach((row) => {
    const r = el('tr');
    row.cells.forEach((cell, i) => {
      const td = el('td', undefined, head[i].num ? 'num' : head[i].wrap ? 'wrap' : '');
      if (cell instanceof Node) td.appendChild(cell); else td.textContent = cell;
      r.appendChild(td);
    });
    if (row.kind) {
      r.addEventListener('mouseenter', () => highlight(row.kind));
      r.addEventListener('mouseleave', () => highlight(null));
    }
    tbody.appendChild(r);
  });
  table.append(thead, tbody);
}

function showModule(info) {
  const [x, y, z] = info.outer_size_mm;
  const cost = info.bom.reduce((sum, b) => sum + (b.price_usd || 0) * b.qty, 0);
  const summary = $('summary');
  summary.replaceChildren();
  [['외형 (핀·바퀴 포함)', `${x} × ${y} × ${z} mm`],
   ['무게', `약 ${info.mass_g} g`],
   ['무게중심 높이', `바닥에서 ${info.center_of_mass_mm[2]} mm`],
   ['부품 수', `${info.part_count}개`],
   ['구매 부품비 (추정)', `약 ${cost.toFixed(0)} 달러, 제작품 가공비 제외`]]
    .forEach(([k, v]) => summary.append(el('dt', k), el('dd', v)));

  fillTable($('bom'),
    [{ text: '품명' }, { text: '수량', num: true }, { text: '무게(g)', num: true }, { text: '단가($)', num: true }, { text: '비고', wrap: true }],
    info.bom.map((b) => {
      const name = el('span');
      const sw = el('span', '', 'swatch');
      sw.style.background = `rgb(${b.color.map((c) => Math.round(c * 255)).join(',')})`;
      name.append(sw, document.createTextNode(b.name));
      return { kind: b.kind, cells: [name, b.qty, b.mass_g, b.price_usd == null ? '-' : b.price_usd.toFixed(1), b.note] };
    }));
}

let defaults = {};
function buildForm(editable, params) {
  const form = $('editForm');
  form.replaceChildren();
  Object.entries(editable).forEach(([key, rule]) => {
    const label = el('label');
    label.htmlFor = 'p_' + key;
    label.append(document.createTextNode(rule.label + ' '), el('small', `${rule.min}~${rule.max}`));
    const input = el('input');
    Object.assign(input, { type: 'number', id: 'p_' + key, name: key, min: rule.min, max: rule.max, step: rule.step, value: params[key] });
    input.addEventListener('input', () => input.classList.toggle('changed', Number(input.value) !== defaults[key]));
    form.append(label, input);
  });
}

async function rebuild() {
  const params = {};
  $('editForm').querySelectorAll('input').forEach((i) => { params[i.name] = Number(i.value); });
  const msg = $('buildMsg'), button = $('rebuild');
  msg.className = '';
  msg.textContent = '설계 코드를 실행하는 중입니다…';
  button.disabled = true;
  try {
    const res = await fetch('/robot/api/build', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ params }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '형상을 만들지 못했습니다.');
    showModule(data.module);
    ensureOption('custom', '바꾼 치수의 모듈', data.glb);
    $('model').value = 'custom';
    await loadModel(data.glb);
    msg.className = 'ok';
    msg.textContent = `완료: ${data.module.outer_size_mm.join(' × ')} mm, 약 ${data.module.mass_g} g. 부품 간섭 없음, 결합 검사 통과.`;
  } catch (e) {
    msg.className = 'error';
    msg.textContent = e.message;
  } finally {
    button.disabled = false;
  }
}

const models = {};
function ensureOption(value, text, url) {
  models[value] = url;
  let option = [...$('model').options].find((o) => o.value === value);
  if (!option) {
    option = el('option', text);
    option.value = value;
    $('model').appendChild(option);
  }
}

function showClusters(clusters, sim, hasVideo) {
  if (clusters) {
    const a = clusters.assumptions;
    $('clusterNote').textContent =
      `바퀴가 미끄러지기 직전까지 낼 수 있는 힘 기준의 단순 계산입니다 (바퀴 마찰 ${a.mu_wheel}, 짐 마찰 ${a.mu_load} 가정).`;
    fillTable($('clusters'),
      [{ text: '형태', wrap: true }, { text: '대수', num: true }, { text: '크기 (mm)' }, { text: '무게(kg)', num: true },
       { text: '미는 힘(N)', num: true }, { text: '밀 수 있는 짐(kg)', num: true }],
      clusters.clusters.map((c) => ({ cells: [c.description, c.modules, c.size_mm.join(' × '), c.mass_kg, c.max_push_N, c.max_load_kg] })));
  }
  if (sim) {
    const v = sim.video;
    $('simNote').textContent =
      `물리 시뮬레이션(MuJoCo) 결과: ${v.load_kg} kg 짐을 1대는 ${(v.moved_m.solo * 100).toFixed(0)} cm, ` +
      `4대 합체는 ${(v.moved_m.team * 100).toFixed(0)} cm 밀었습니다. 결합부에 걸린 최대 힘은 ${v.peak_joint_force_N} N 입니다.`;
    fillTable($('simTable'),
      [{ text: '형태' }, { text: '시뮬레이션 (kg)', num: true }, { text: '단순 계산 (kg)', num: true }],
      sim.max_load_by_shape.map((r) => ({ cells: [r.shape, r.sim_max_load_kg, r.estimate_max_load_kg] })));
  }
  if (hasVideo) $('simVideo').src = '/robot/files/sim_push.mp4'; else $('simVideo').remove();
}

function showFiles(drawings, steps) {
  const names = { 'M1-001_body': '본체 제작 도면', 'M1-000_assembly': '조립도·부품표' };
  const groups = {};
  drawings.forEach((f) => { (groups[f.replace(/_drawing\.\w+$/, '')] ||= []).push(f); });
  const list = $('drawings');
  list.replaceChildren();
  Object.entries(groups).forEach(([stem, files]) => {
    const li = el('li', (names[stem] || stem) + ': ');
    files.forEach((f, i) => {
      const a = el('a', f.split('.').pop().toUpperCase());
      a.href = '/robot/files/' + f;
      a.target = '_blank';
      li.append(a, document.createTextNode(i < files.length - 1 ? ' · ' : ''));
    });
    list.appendChild(li);
  });
  const stepList = $('steps');
  stepList.replaceChildren();
  steps.forEach((f) => {
    const li = el('li'), a = el('a', f);
    a.href = '/robot/files/' + f;
    a.download = f;
    li.appendChild(a);
    stepList.appendChild(li);
  });
}

// ------------------------------------------------------------ 시작
document.querySelectorAll('.tab').forEach((tab) => tab.addEventListener('click', () => {
  document.querySelectorAll('.tab, .tabpane').forEach((n) => n.classList.remove('active'));
  tab.classList.add('active');
  $('tab-' + tab.dataset.tab).classList.add('active');
}));
$('showLid').addEventListener('change', applyDisplayOptions);
$('ghostBody').addEventListener('change', applyDisplayOptions);
$('resetView').addEventListener('click', () => {
  if (!homeView) return;
  camera.position.copy(homeView.position);
  controls.target.copy(homeView.target);
});
$('model').addEventListener('change', (e) => loadModel(models[e.target.value]));
$('rebuild').addEventListener('click', rebuild);
$('resetParams').addEventListener('click', () => {
  $('editForm').querySelectorAll('input').forEach((i) => { i.value = defaults[i.name]; i.classList.remove('changed'); });
});

(async function start() {
  resize();
  const data = await (await fetch('/robot/api/data')).json();
  if (!data.module) {
    $('status').textContent = '설계 결과 파일이 없습니다. python robot-cad/module1.py 를 먼저 실행하세요.';
    return;
  }
  defaults = data.module.params;
  ensureOption('module1', '모듈 1대', '/robot/files/module1.glb');
  (data.clusters ? data.clusters.clusters : []).filter((c) => c.modules > 1)
    .forEach((c) => ensureOption(c.name, '합체: ' + c.description, `/robot/files/cluster_${c.name}.glb`));
  showModule(data.module);
  buildForm(data.editable, data.module.params);
  showClusters(data.clusters, data.sim, data.hasVideo);
  showFiles(data.drawings, data.steps);
  await loadModel(models.module1);
})();
