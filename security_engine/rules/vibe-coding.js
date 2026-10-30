// Semgrep 규칙 테스트용 파일 (실행되는 코드가 아님).
// 'ruleid' 주석 바로 아래 줄은 반드시 걸려야 하고, 'ok' 주석 아래 줄은 걸리면 안 된다.
// 실행: semgrep --test --metrics=off security_engine/rules
const { exec } = require("child_process");
const cors = require("cors");
const jwt = require("jsonwebtoken");

// ruleid: public-env-exposes-secret
const admin = process.env.NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY;
// ruleid: public-env-exposes-secret
const pw = import.meta.env.VITE_ADMIN_PASSWORD;
// ok: public-env-exposes-secret
const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
// ok: public-env-exposes-secret
const serverOnly = process.env.SUPABASE_SERVICE_ROLE_KEY;

app.get("/u", (req, res) => {
  // ruleid: js-eval-dynamic
  eval(req.query.expr);
  // ok: js-eval-dynamic
  eval("1 + 1");

  // ruleid: js-new-function-dynamic
  const fn = new Function("a", req.body.code);
  // ok: js-new-function-dynamic
  const add = new Function("a", "b", "return a + b");

  // ruleid: node-command-injection
  exec("ls " + req.query.dir);
  // ruleid: node-command-injection
  exec(`ping ${req.query.host}`);
  // ok: node-command-injection
  exec("ls -al");

  // ruleid: sql-string-concat
  db.query("SELECT * FROM users WHERE id = " + req.query.id);
  // ruleid: sql-string-concat
  db.query(`SELECT * FROM users WHERE name = '${req.query.name}'`);
  // ok: sql-string-concat
  db.query("SELECT * FROM users WHERE id = ?", [req.query.id]);

  // ruleid: dom-innerhtml-dynamic
  document.getElementById("out").innerHTML = req.query.q;
  // ok: dom-innerhtml-dynamic
  document.getElementById("out").innerHTML = "<b>hello</b>";
  // ok: dom-innerhtml-dynamic
  document.getElementById("out").innerHTML = DOMPurify.sanitize(req.query.q);

  // ruleid: document-write-dynamic
  document.write(location.hash);
  // ok: document-write-dynamic
  document.write("<p>static</p>");

  // ruleid: cors-allow-any-origin
  res.setHeader("Access-Control-Allow-Origin", "*");
  // ok: cors-allow-any-origin
  res.setHeader("Access-Control-Allow-Origin", "https://my-site.com");

  // ruleid: jwt-hardcoded-secret
  const t = jwt.sign({ id: 1 }, "changeme");
  // ok: jwt-hardcoded-secret
  const t2 = jwt.sign({ id: 1 }, process.env.JWT_SECRET);

  // ruleid: token-in-localstorage
  localStorage.setItem("accessToken", t);
  // ok: token-in-localstorage
  localStorage.setItem("theme", "dark");
});

// ruleid: cors-allow-any-origin
app.use(cors({ origin: "*" }));
// ok: cors-allow-any-origin
app.use(cors({ origin: ["https://my-site.com"] }));

// ruleid: tls-verify-disabled-node
const agent = new https.Agent({ rejectUnauthorized: false });
// ok: tls-verify-disabled-node
const safeAgent = new https.Agent({ keepAlive: true });
