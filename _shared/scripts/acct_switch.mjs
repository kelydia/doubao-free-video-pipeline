// 豆包网页版账号轮换通用模块（跨任务复用）
// 操作规范见 _shared/专题手册/05_账号轮换与额度自动切换规范.md
// 用法：
//   const A = await import("file:///D:/dsh_space/豆包免费视频生成/_shared/scripts/acct_switch.mjs");
//   const r = await A.switchToFreshAccount(page);   // quota 命中时调用
//
// 硬约束（手册 04 §7 / 操作手册 §6）：
//   1. 必须在同一次 taskSpace 会话内派发完整 pointer+mouse 事件序列，不要跨 claim 重载。
//   2. 左下角账号按钮 y≈738-770，账号面板条目 y≈580-660；读面板时必须排除 y>=700 的按钮本身。
//   3. 账号名是「用户xxxxxxx」这类字母数字混合，正则不能用 /用户\d+/（会漏掉）。

import fs from "node:fs";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 已知账号池（2026-11-15 实测；面板动态读取为准，此常量仅用于台账与开工预检）
export const KNOWN_ACCOUNTS = []; // 示例账号已脱敏；运行时以页面动态读取为准

export async function currentAccount(page) {
  return await page.evaluate(() => {
    const b = [...document.querySelectorAll("button")]
      .map((e) => (e.innerText || "").trim())
      .find((t) => /^用户[A-Za-z0-9]+$/.test(t));
    return b || null;
  });
}

export async function quotaExhausted(page) {
  return await page.evaluate(() =>
    /今日视频生成免费额度已用完|额度已用完/.test(document.body.innerText || ""));
}

async function openAccountPanel(page) {
  return await page.evaluate(() => {
    const btn = [...document.querySelectorAll("button")]
      .find((e) => /用户[A-Za-z0-9]+/.test((e.innerText || "").trim()));
    if (!btn) return null;
    const b = btn.getBoundingClientRect();
    const x = b.x + b.width / 2, y = b.y + b.height / 2;
    const mk = (t, C) => new C(t, {
      bubbles: true, cancelable: true, clientX: x, clientY: y,
      button: 0, buttons: 1, pointerId: 1, pointerType: "mouse", isPrimary: true,
    });
    btn.dispatchEvent(mk("pointerover", PointerEvent));
    btn.dispatchEvent(mk("pointerenter", PointerEvent));
    btn.dispatchEvent(mk("pointerdown", PointerEvent));
    btn.dispatchEvent(mk("mousedown", MouseEvent));
    btn.dispatchEvent(mk("pointerup", PointerEvent));
    btn.dispatchEvent(mk("mouseup", MouseEvent));
    btn.dispatchEvent(mk("click", MouseEvent));
    return { x: Math.round(x), y: Math.round(y), text: (btn.innerText || "").trim() };
  });
}

// 面板已打开时调用；只取 y<700 的条目，避开左下角账号按钮自身
async function readPanelAccounts(page) {
  return await page.evaluate(() => {
    const names = [...document.querySelectorAll("div,button,a,span,li")]
      .map((e) => ({ t: (e.innerText || "").trim(), r: e.getBoundingClientRect() }))
      .filter((o) => /^用户[A-Za-z0-9]+$/.test(o.t)
        && o.r.y < 700 && o.r.width > 40 && o.r.height > 12 && o.r.height < 100)
      .map((o) => o.t);
    return [...new Set(names)];
  });
}

async function clickAccountEntry(page, targetName) {
  return await page.evaluate((name) => {
    const cands = [...document.querySelectorAll("div,button,a,span,li")]
      .filter((e) => (e.innerText || "").trim() === name)
      .map((e) => ({ e, r: e.getBoundingClientRect() }))
      .filter((o) => o.r.y < 700 && o.r.width > 40 && o.r.height > 12 && o.r.height < 100);
    if (!cands.length) return { clicked: false, count: 0, name };
    // 取最外层（宽度最大）的条目，避免点到内层 span
    cands.sort((a, b) => b.r.width - a.r.width);
    const el = cands[0].e, r = cands[0].r;
    const x = r.x + r.width / 2, y = r.y + r.height / 2;
    const mk = (t, C) => new C(t, {
      bubbles: true, cancelable: true, clientX: x, clientY: y,
      button: 0, buttons: 1, pointerId: 1, pointerType: "mouse", isPrimary: true,
    });
    el.dispatchEvent(mk("pointerover", PointerEvent));
    el.dispatchEvent(mk("pointerdown", PointerEvent));
    el.dispatchEvent(mk("mousedown", MouseEvent));
    el.dispatchEvent(mk("pointerup", PointerEvent));
    el.dispatchEvent(mk("mouseup", MouseEvent));
    el.dispatchEvent(mk("click", MouseEvent));
    return { clicked: true, count: cands.length, name, x: Math.round(x), y: Math.round(y) };
  }, targetName);
}

async function freshHome(page) {
  await page.goto("https://www.doubao.com/chat/");
  await sleep(9000);
  await page.keyboard.press("Escape");
  await sleep(1500);
}

// 切到指定账号；已是该账号则直接返回 unchanged
export async function switchAccount(page, target) {
  const before = await currentAccount(page);
  if (before === target) return { ok: true, unchanged: true, before, after: before };
  await freshHome(page);
  const opened = await openAccountPanel(page);
  if (!opened) return { ok: false, reason: "account button not found", before, target };
  await sleep(3000);
  const accounts = await readPanelAccounts(page);
  if (!accounts.includes(target)) {
    return { ok: false, reason: "target not in account panel", before, target, accounts };
  }
  const clicked = await clickAccountEntry(page, target);
  await sleep(6000);
  const after = await currentAccount(page);
  return { ok: after === target, before, after, target, accounts, clicked };
}

// ★ 额度不足时的标准动作：探测面板 → 选一个与当前不同的账号 → 切换 → 校验
export async function switchToFreshAccount(page) {
  await freshHome(page);
  const before = await currentAccount(page);
  const opened = await openAccountPanel(page);
  if (!opened) return { ok: false, reason: "account button not found", before };
  await sleep(3000);
  const accounts = await readPanelAccounts(page);
  const target = accounts.find((n) => n !== before);
  if (!target) {
    return { ok: false, reason: "no alternate account in panel", before, accounts };
  }
  const clicked = await clickAccountEntry(page, target);
  await sleep(6000);
  const after = await currentAccount(page);
  return { ok: after === target, before, after, target, accounts, clicked };
}

// 额度台账：每行 时间 / 任务 / 镜头 / 账号 / 结果 / 备注
export function appendLedger(path, row) {
  const line = "| " + [
    new Date().toISOString().replace("T", " ").slice(0, 19),
    row.task || "-", row.shot || "-", row.account || "-",
    row.result || "-", (row.note || "-").replace(/\|/g, "/"),
  ].join(" | ") + " |\n";
  fs.appendFileSync(path, line, "utf-8");
  return line.trim();
}
