// demo-vulnerable-site: 72hours 실검증용 '취약한 사이트' (데모 전용, 배포 금지)
// 일부러 취약하게 만든 코드입니다. 보안엔진이 탐지하고 Red–Blue가 수정 전/후를 확인합니다.
"use strict";

const express = require("express");
const jwt = require("jsonwebtoken");
const { DatabaseSync } = require("node:sqlite");

// [취약점 3] 하드코딩된 JWT 서명 키 (CWE-798) — 실제로는 환경변수로 옮겨야 함. 데모용 가짜 값.
const JWT_SECRET = "demo-insecure-key";

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

function createApp() {
  const app = express();
  const db = makeDb();

  app.get("/", (_req, res) => {
    res.type("text/plain").send("demo-vulnerable-site: /api/orders?orderId=1, /search?q=커피, /token");
  });

  // [취약점 1] SQL 인젝션 (CWE-89): 사용자 입력을 쿼리 문자열에 그대로 이어 붙임
  app.get("/api/orders", (req, res) => {
    const orderId = req.query.orderId;
    try {
      const rows = db.query("SELECT * FROM orders WHERE id = " + orderId);
      res.json(rows);
    } catch (e) {
      res.status(400).json({ error: "Invalid orderId parameter" });
    }
  });

  // [취약점 2] 반사형 XSS (CWE-79): 입력을 이스케이프 없이 HTML에 출력
  app.get("/search", (req, res) => {
    const q = req.query.q || "";
    res.type("html").send(`<!doctype html><h1>"${q}" 검색 결과</h1><p>결과가 없습니다.</p>`);
  });

  // 하드코딩 키로 토큰 발급 (취약점 3이 걸리는 지점)
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
