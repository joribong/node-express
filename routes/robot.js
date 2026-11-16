// 로봇 설계 뷰어: 3D 파일·도면·부품표를 보여 주고, 치수를 바꿔 다시 만든다.
var express = require('express');
var path = require('path');
var fs = require('fs');
var execFile = require('child_process').execFile;

var router = express.Router();
var CAD_DIR = path.join(__dirname, '..', 'robot-cad');
var OUT_DIR = path.join(CAD_DIR, 'out');
var CUSTOM_DIR = path.join(OUT_DIR, 'custom');

// 화면에서 바꿀 수 있는 치수와 허용 범위 (mm)
var EDITABLE = {
  length: { label: '본체 길이', min: 80, max: 300, step: 5 },
  width: { label: '본체 폭', min: 80, max: 300, step: 5 },
  height: { label: '본체 높이', min: 45, max: 150, step: 5 },
  wheel_r: { label: '바퀴 반지름', min: 10, max: 40, step: 1 },
  wheel_x: { label: '바퀴 축 위치 (중심에서)', min: 20, max: 130, step: 1 },
  ground_clearance: { label: '바닥 틈', min: 2, max: 20, step: 1 },
  pin_dx: { label: '결합 핀 좌우 거리', min: 8, max: 40, step: 1 },
  pin_h: { label: '결합 핀 길이', min: 3, max: 15, step: 0.5 },
  pcb_z: { label: '기판 높이', min: 25, max: 120, step: 1 }
};

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(path.join(OUT_DIR, file), 'utf8'));
  } catch (e) {
    return null;
  }
}

function listFiles(pattern) {
  try {
    return fs.readdirSync(OUT_DIR).filter(function (f) { return pattern.test(f); }).sort();
  } catch (e) {
    return [];
  }
}

router.get('/', function (req, res) {
  res.render('robot', { title: '모듈 로봇 설계 뷰어' });
});

// 화면에 필요한 자료를 한 번에 내려 준다
router.get('/api/data', function (req, res) {
  res.json({
    module: readJson('module1_info.json'),
    clusters: readJson('clusters.json'),
    sim: readJson('sim_results.json'),
    editable: EDITABLE,
    drawings: listFiles(/_drawing\.(pdf|dxf|svg)$/),
    steps: listFiles(/\.step$/),
    hasVideo: fs.existsSync(path.join(OUT_DIR, 'sim_push.mp4'))
  });
});

var building = false;

// 치수를 바꿔 모듈을 다시 만든다 (파이썬 설계 코드를 실행)
router.post('/api/build', function (req, res) {
  var input = (req.body && req.body.params) || {};
  var params = {};
  var keys = Object.keys(input);
  for (var i = 0; i < keys.length; i++) {
    var key = keys[i];
    var rule = EDITABLE[key];
    var value = Number(input[key]);
    if (!rule || !isFinite(value)) {
      return res.status(400).json({ error: '바꿀 수 없는 치수입니다: ' + key });
    }
    if (value < rule.min || value > rule.max) {
      return res.status(400).json({ error: rule.label + ' 값은 ' + rule.min + '~' + rule.max + ' 사이여야 합니다.' });
    }
    params[key] = value;
  }
  if (building) {
    return res.status(429).json({ error: '이전 형상을 만드는 중입니다. 잠시 후 다시 시도하세요.' });
  }
  building = true;
  var args = [path.join(CAD_DIR, 'module1.py'), '--params', JSON.stringify(params), '--out', CUSTOM_DIR, '--no-drawings'];
  execFile(process.env.PYTHON || 'python3', args, { timeout: 120000 }, function (err, stdout, stderr) {
    building = false;
    if (err) {
      var lines = String(stderr || err.message).trim().split('\n');
      var last = lines[lines.length - 1];
      var message = err.code === 'ENOENT' ? '이 컴퓨터에 파이썬이 없어 형상을 다시 만들 수 없습니다.'
        : /No module named/.test(last) ? '파이썬 설계 도구(build123d)가 설치되지 않았습니다. robot-cad/README.md 를 참고하세요.'
        : last;
      return res.status(422).json({ error: message });
    }
    var info = null;
    try {
      info = JSON.parse(fs.readFileSync(path.join(CUSTOM_DIR, 'module1_info.json'), 'utf8'));
    } catch (e) {
      return res.status(500).json({ error: '결과 파일을 읽지 못했습니다.' });
    }
    res.json({ module: info, glb: '/robot/files/custom/module1.glb?t=' + Date.now(), step: '/robot/files/custom/module1.step' });
  });
});

router.use('/files', express.static(OUT_DIR));

module.exports = router;
