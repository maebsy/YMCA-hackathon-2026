// demo-vulnerable-site 기준 수정본 (Blue가 내야 할 수정의 예시). 실검증 API·테스트가 after 사본에 덮어씁니다.
// 바뀐 곳: [수정 1] 파라미터 바인딩, [수정 2] 출력 이스케이프, [수정 3] 서명 키를 환경변수로.
"use strict";

const express = require("express");
const jwt = require("jsonwebtoken");
const { DatabaseSync } = require("node:sqlite");
const crypto = require("node:crypto");

// [수정 3] 서명 키는 환경변수에서. 없으면 실행할 때마다 임의 키(재시작하면 기존 토큰 무효).
const JWT_SECRET = process.env.JWT_SECRET || crypto.randomBytes(32).toString("hex");

// 외부 DB 없이 켜지도록 메모리 SQLite를 쓰되, 흔한 작성 패턴처럼 db.query(sql)로 감쌉니다.
function makeDb() {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(`CREATE TABLE orders (id INTEGER PRIMARY KEY, customer TEXT, item TEXT, total INTEGER)`);
  const rows = [
    [1, "김민지", "아메리카노", 4500],
    [2, "이수호", "카페라떼", 5000],
    [3, "박지우", "콜드브루", 5500],
  ];
  const ins = sqlite.prepare("INSERT INTO orders (id, customer, item, total) VALUES (?, ?, ?, ?)");
  for (const r of rows) ins.run(...r);
  return {
    query(sql, ...params) {
      return sqlite.prepare(sql).all(...params);
    },
  };
}

const HTML_ESCAPE = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => HTML_ESCAPE[c]);
}

function createApp() {
  const app = express();
  const db = makeDb();

  app.get("/", (_req, res) => {
    res.type("text/plain").send("demo-vulnerable-site: /api/orders?orderId=1, /search?q=커피, /token");
  });

  // [수정 1] 입력은 쿼리 문자열에 붙이지 않고 ? 자리에 값으로 넘김 (파라미터 바인딩)
  app.get("/api/orders", (req, res) => {
    const orderId = req.query.orderId;
    try {
      const rows = db.query("SELECT * FROM orders WHERE id = ?", orderId);
      res.json(rows);
    } catch (e) {
      res.status(400).json({ error: "Invalid orderId parameter" });
    }
  });

  // [수정 2] HTML에 넣기 전에 특수문자를 이스케이프
  app.get("/search", (req, res) => {
    const q = escapeHtml(req.query.q || "");
    res.type("html").send(`<!doctype html><h1>"${q}" 검색 결과</h1><p>결과가 없습니다.</p>`);
  });

  app.get("/token", (req, res) => {
    const token = jwt.sign({ user: req.query.user || "guest" }, JWT_SECRET, { expiresIn: "1h" });
    res.json({ token });
  });

  return app;
}

if (require.main === module) {
  const port = process.env.PORT || 3100;
  createApp().listen(port, "127.0.0.1", () => {
    console.log(`demo-vulnerable-site on http://127.0.0.1:${port}`);
  });
}

module.exports = { createApp };
