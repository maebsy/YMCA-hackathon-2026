// 기능 테스트: 수정(패치) 후에도 이게 통과해야 '기능 보존'으로 봅니다.
"use strict";

const { test, before, after } = require("node:test");
const assert = require("node:assert");
const { createApp } = require("../server");

let server, base;

before(async () => {
  await new Promise((resolve) => {
    server = createApp().listen(0, "127.0.0.1", resolve);
  });
  base = `http://127.0.0.1:${server.address().port}`;
});

after(() => server && server.close());

test("정상 주문 조회는 해당 주문 1건만 반환", async () => {
  const res = await fetch(`${base}/api/orders?orderId=1`);
  assert.equal(res.status, 200);
  const rows = await res.json();
  assert.equal(rows.length, 1);
  assert.equal(rows[0].customer, "김민지");
});

test("검색 페이지가 응답", async () => {
  const res = await fetch(`${base}/search?q=${encodeURIComponent("커피")}`);
  assert.equal(res.status, 200);
  const html = await res.text();
  assert.ok(html.includes("검색 결과"));
  // 검색어를 지워 버리는 '수정'은 공격은 막아도 기능이 깨진 것입니다. 입력값은 이스케이프해서 계속 보여야 합니다
  assert.ok(html.includes("커피"), "검색어가 결과 화면에 보여야 함");
});

test("토큰 발급이 응답", async () => {
  const res = await fetch(`${base}/token?user=minji`);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.ok(typeof body.token === "string" && body.token.length > 0);
});
