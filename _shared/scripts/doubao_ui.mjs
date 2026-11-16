// 豆包网页版 · 校验层实现（不是规范）
//
// 用户 2026-11-16 要求：「通过 ego_browser 操作网页版豆包，应该形成经验或者 skill，
// 不需要每次去重新看页面、分析，只有原经验或者 skill 操作失败了，才该去查看、分析，
// 更新经验、skill。」—— 后续讨论定为「简约、直接、稳定；稳定 > 省token > 省时间；取舍交人工」。
//
// 唯一权威规范：_shared/豆包网页版操作手册.md（最小 SOP）
// 本模块只是把「每次提交前的 5 条确定性校验」做成可调用的函数；UI 路径表、变更登记是实现细节，不是规范。
//
// 稳定第一：每个入口都返回结构化状态，校验不过就明确停下，不猜、不自动蒙一条路径。
// 次要优化：已知路径回退链减少重复探查；全部失效才 probeUi() 落盘快照并返回 PROBE_NEEDED，
// 此时按最小 SOP「不确定就停，交人工」处理，并把新路径回写 UI_PATHS + UI_CHANGELOG。
//
// 所有路径均来自实测记录，来源标在每条注释里。
// 本文件 UTF-8，含中文，必须用 write/edit 工具维护，禁止 PowerShell 读写。
// 用法（在 .mjs 脚本里，不要放进 -e 参数）：
//   const D = await import("file:///D:/dsh_space/豆包免费视频生成/_shared/scripts/doubao_ui.mjs");
//   const r = await D.enterImageMode(page);
//   if (!r.ok) throw new Error("PROBE_NEEDED " + r.probeFile);

import fs from "node:fs";
import path from "node:path";

export const HOME = "https://www.doubao.com/chat/";
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── UI 变更登记表 ────────────────────────────────────────────────────────────
// 每次「探查后回写」都在这里追加一行（实现细节，不进最小 SOP）。
export const UI_CHANGELOG = [
  {
    date: "2026-11-11",
    layout: "v1",
    change: "首页底部技能栏直接有 <button>「图像生成」/「视频生成」",
    paths: ["img-p1-bottom-button", "vid-p1-bottom-button"],
    source: "实测：_shared/豆包网页版操作手册.md §2/§8、gen2_img.mjs",
  },
  {
    date: "2026-11-15",
    layout: "v2",
    change: "freshChat 不切模式（模式残留坑）；页面可能已在图像模式，此时「图像生成」按钮消失，模型选择器显示 Seedream 5.0 Flash",
    paths: ["img-p0-already", "vid-p0-already"],
    source: "实测：round-02.mjs、gen_img.mjs 首跑 imgmode false 后修复",
  },
  {
    date: "2026-11-16",
    layout: "v3",
    change: "底部技能栏只剩 对话/项目/视频生成/更多技能/快速；「图像生成」移入「更多技能」菜单，菜单项是 LI（不是 button），文本「图像生成」约 x=303,y=365,w=567,h=32；技能卡显示 Seedream 5.5",
    paths: ["img-p2-more-skills-li", "vid-p2-more-skills-li"],
    source: "实测：round-09/10/11/12 探查（这是最后一次手写探查脚本，之后收敛进本模块）",
  },
];

// ── 已知路径登记表（唯一需要人工维护的地方）────────────────────────────────
// 顺序 = 优先级。新增条目请用 edit 追加，并在 UI_CHANGELOG 登记。
const IMAGE_PATHS = [
  { id: "img-p0-already", kind: "already" },                                  // 已在图像模式
  { id: "img-p1-bottom-button", kind: "button", text: "图像生成" },            // v1/v2 旧布局
  { id: "img-p2-more-skills-li", kind: "more-skills-li", itemText: "图像生成" }, // v3 新布局
];
const VIDEO_PATHS = [
  { id: "vid-p0-already", kind: "already" },
  { id: "vid-p1-bottom-button", kind: "button", text: "视频生成" },
  { id: "vid-p2-more-skills-li", kind: "more-skills-li", itemText: "视频生成" },
];

const PROBE_DIR = "D:/dsh_space/豆包免费视频生成/_shared/scripts/.cache/work";

// ── 状态判定 ────────────────────────────────────────────────────────────────
export async function isImageMode(page) {
  // Seedream 模型选择器只在图像模式出现；不能用 placeholder（CSS 伪元素不在 innerText）。
  return page.evaluate(() =>
    /Seedream|seedream|图像模型|图片模型/.test(document.body.innerText || ""));
}

export async function isVideoMode(page) {
  // 规格按钮文本形如「9:16 · 5s」。
  return page.evaluate(() => /·\s*\d+s/.test(document.body.innerText || ""));
}

export async function hasCaptcha(page) {
  return page.evaluate(() => !!document.querySelector("iframe[src*='verifycenter']"));
}

// ── 首页 / 登录态预检 ────────────────────────────────────────────────────────
export async function openHome(page, opts = {}) {
  const settleMs = opts.settleMs ?? 7000;
  await page.goto(HOME);
  await sleep(settleMs);
  await page.keyboard.press("Escape");
  await sleep(1200);
  const state = await page.evaluate(() => {
    const t = document.body.innerText || "";
    return {
      url: location.href,
      account: (t.match(/用户[A-Za-z0-9]+/) || [null])[0],
      loginWall: /扫码登录|登录后可使用|立即登录/.test(t),
      captcha: !!document.querySelector("iframe[src*='verifycenter']"),
      hasEditor: document.querySelectorAll('[contenteditable="true"]').length,
      tail: t.slice(-240).replace(/\n+/g, "|"),
    };
  });
  return {
    ok: !state.loginWall && !state.captcha && state.hasEditor > 0,
    ...state,
  };
}

// 开工预检：登录态 + 当前账号 + 额度（额度函数来自同目录 acct_switch.mjs）
export async function preflight(page, opts = {}) {
  const home = await openHome(page, opts);
  const A = await import("./acct_switch.mjs");
  return {
    ...home,
    quotaExhausted: await A.quotaExhausted(page),
    account: home.account || await A.currentAccount(page),
  };
}

// ── 单条路径尝试 ────────────────────────────────────────────────────────────
async function clickByText(page, text, tags) {
  // 历史坑：evaluate 里的 el.click() 在部分账号下不生效，必须 page.mouse.move + click。
  const box = await page.evaluate(({ text, tags }) => {
    const vis = (e) => {
      const r = e.getBoundingClientRect();
      return e.offsetParent !== null && r.width > 0 && r.height > 0;
    };
    const el = [...document.querySelectorAll(tags)]
      .filter(vis)
      .find((e) => (e.innerText || "").trim() === text);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  }, { text, tags });
  if (!box) return false;
  await page.mouse.move(box.x, box.y);
  await sleep(300);
  await page.mouse.click(box.x, box.y);
  return true;
}

async function clickMoreSkillsItem(page, itemText) {
  const opened = await clickByText(page, "更多技能", "button,[role=button],div,span");
  if (!opened) return { clicked: false, why: "no 更多技能 entry" };
  await sleep(1500);
  // v3 实测：菜单项是 LI，不是 button；文本恰为「图像生成」/「视频生成」。
  const hit = await clickByText(page, itemText,
    "li,[role=menuitem],button,[data-radix-popper-content-wrapper] div,[data-radix-popper-content-wrapper] span");
  return { clicked: hit, why: hit ? "ok" : "item not found after opening menu" };
}

async function tryPath(page, p) {
  switch (p.kind) {
    case "already":
      return { clicked: false, why: "handled by p0 check" };
    case "button":
      return { clicked: await clickByText(page, p.text, "button,[role=button]") };
    case "more-skills-li":
      return await clickMoreSkillsItem(page, p.itemText);
    default:
      return { clicked: false, why: "unknown kind " + p.kind };
  }
}

// ── 失败才调用：结构化 DOM 快照 ─────────────────────────────────────────────
// 这是本模块唯一「重新看页面」的出口，由 enterImageMode/enterVideoMode 自动调用。
// 调用方拿到 PROBE_NEEDED 后应只看这个快照文件，不要再写新的探查脚本。
export async function probeUi(page, meta = {}) {
  const snap = await page.evaluate(() => {
    const vis = (e) => {
      const r = e.getBoundingClientRect();
      return e.offsetParent !== null && r.width > 0 && r.height > 0;
    };
    const pick = (sel) => [...document.querySelectorAll(sel)].filter(vis).map((e) => {
      const r = e.getBoundingClientRect();
      return {
        tag: e.tagName,
        text: (e.innerText || "").trim().slice(0, 60),
        cls: (e.className || "").toString().slice(0, 80),
        role: e.getAttribute("role"),
        x: Math.round(r.x), y: Math.round(r.y),
        w: Math.round(r.width), h: Math.round(r.height),
      };
    });
    return {
      url: location.href,
      title: document.title,
      bodyTail: (document.body.innerText || "").slice(-600).replace(/\n+/g, "|"),
      buttons: pick("button").slice(0, 80),
      listItems: pick("li,[role=menuitem]").slice(0, 80),
      candidates: pick("button,li,[role=menuitem],[data-radix-popper-content-wrapper] *")
        .filter((x) => /生成|技能|更多|Seedream|Seedance|比例|时长/.test(x.text))
        .slice(0, 80),
      poppers: pick("[data-radix-popper-content-wrapper]"),
    };
  });
  fs.mkdirSync(PROBE_DIR, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const file = path.join(PROBE_DIR, "doubao_ui_probe_" + stamp + ".json");
  fs.writeFileSync(file, JSON.stringify({ ...meta, snap }, null, 1), "utf-8");
  return { file, snap };
}

// ── 主入口：进入图像 / 视频模式 ──────────────────────────────────────────────
async function enterMode(page, { paths, already, tag, opts = {} }) {
  // 每次先开新会话，避免「模式残留」（freshChat 不切模式，11-15 最痛的坑）。
  const home = await openHome(page, opts);
  if (!home.ok) return { ok: false, reason: "HOME_NOT_READY", home };

  const tried = [];
  if (await already(page)) return { ok: true, via: tag + "-p0-already", tried, home };

  for (const p of paths) {
    if (p.kind === "already") { tried.push(p.id + ": not already"); continue; }
    const r = await tryPath(page, p);
    tried.push(p.id + ": " + JSON.stringify(r));
    if (r.clicked) {
      await sleep(2500);
      if (await already(page)) return { ok: true, via: p.id, tried, home };
      tried.push(p.id + ": clicked but mode check failed");
    }
  }

  // 全部已知路径失败 → 唯一允许的探查
  const probe = await probeUi(page, { tag, tried });
  return {
    ok: false,
    reason: "PROBE_NEEDED",
    probeFile: probe.file,
    tried,
    hint: "已知路径全部失效。按最小 SOP「不确定就停，交人工」处理：只读 probeFile 快照，由人工决定是否回写 UI_PATHS + UI_CHANGELOG 并重跑；不自动蒙一条路径。",
  };
}

export function enterImageMode(page, opts = {}) {
  return enterMode(page, {
    paths: IMAGE_PATHS, already: isImageMode, tag: "img", opts,
  });
}

export function enterVideoMode(page, opts = {}) {
  return enterMode(page, {
    paths: VIDEO_PATHS, already: isVideoMode, tag: "vid", opts,
  });
}

// ── 基础提交操作（自包含，替代每个任务目录里复制一份 ui.mjs）────────────────
export async function freshChat(page) {
  await openHome(page, { settleMs: 9000 });
  await openHome(page, { settleMs: 4000 });
}

export async function typePrompt(page, text) {
  return page.evaluate((t) => {
    const el = document.querySelector('[contenteditable="true"]');
    if (!el) return "no-editor";
    el.focus();
    document.execCommand("selectAll");
    document.execCommand("delete");
    const dt = new DataTransfer();
    dt.setData("text/plain", t);
    el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    if ((el.innerText || "").trim().length < 20) document.execCommand("insertText", false, t);
    return String((el.innerText || "").length);
  }, text);
}

export async function sendPrompt(page) {
  // 找 svg class 含 send-msg-btn|size-18 的最右 button；不要坐标点右下角（会点麦克风）。
  return page.evaluate(() => {
    const cands = [...document.querySelectorAll("button")].filter((b) => {
      const svg = b.querySelector("svg");
      if (!svg) return false;
      const c = (svg.getAttribute("class") || "") + " " + (b.className || "");
      return /send-msg-btn|size-18/.test(c);
    });
    const b = cands.sort((a, z) => z.getBoundingClientRect().x - a.getBoundingClientRect().x)[0];
    if (!b) return false;
    b.click();
    return true;
  });
}

export async function attachRefs(page, files) {
  // 手册坑：thumb-image 计数常误报 0，用 img[src^="blob:"] 计数才准。
  await page.evaluate(() => {
    document.querySelectorAll("input[type=file]").forEach((i, k) => i.setAttribute("data-fidx", String(k)));
  });
  const pick = await page.evaluate(() => {
    const ins = [...document.querySelectorAll("input[type=file]")];
    const i = ins.findIndex((x) => /\.png|\.jpe?g/.test(x.accept || ""));
    return i >= 0 ? i : 0;
  });
  await page.setInputFiles(`input[data-fidx="${pick}"]`, files);
  await sleep(7000);
  return page.evaluate(() => ({
    thumbs: document.querySelectorAll('[class*="thumb-image"]').length,
    blobs: [...document.querySelectorAll("img")].filter((x) => x.src.startsWith("blob:")).length,
  }));
}

export async function confirmIfNeeded(page) {
  // 长提示词会先回「确认后我再开始生成视频」→ 补发一句，不要重复点发送。
  const need = await page.evaluate(() =>
    /确认后我再开始生成视频|视频生成参数确认/.test(document.body.innerText || ""));
  if (!need) return false;
  await typePrompt(page, "确认，请直接开始生成视频");
  await sleep(1500);
  await sendPrompt(page);
  return true;
}

// ── 等待 / 下载（把 wait.mjs 与 grab.mjs 的实测逻辑收敛进来）────────────────
export async function waitVideo(page, { rounds = 100, stepMs = 6000 } = {}) {
  for (let i = 0; i < rounds; i++) {
    await sleep(stepMs);
    const s = await page.evaluate(() => {
      const t = document.body.innerText || "";
      return {
        done: /你的视频生成好了|视频生成好了|视频已生成/.test(t),
        quota: /今日视频生成免费额度已用完|额度已用完/.test(t),
        failed: /视频生成失败，生成额度未扣除/.test(t),
        captcha: !!document.querySelector("iframe[src*='verifycenter']"),
        vids: [...document.querySelectorAll("video")].filter((v) => v.currentSrc).length,
      };
    });
    if (s.quota || s.failed || s.captcha || s.done || s.vids > 0) return { ...s, waitedMs: (i + 1) * stepMs };
  }
  return { done: false, quota: false, failed: false, captcha: false, vids: 0, timeout: true };
}

export async function grabVideo(page, outPath) {
  await page.evaluate(() => {
    const s = [...document.querySelectorAll("div")].find((d) =>
      d.className.toString().includes("v_list_scroller") && d.scrollHeight > d.clientHeight + 30);
    if (s) s.scrollTop = s.scrollHeight; else window.scrollTo(0, document.body.scrollHeight);
  });
  await sleep(2000);
  const box = await page.evaluate(() => {
    const im = [...document.querySelectorAll("img")].filter((i) => i.className.toString().includes("cover-u1rIsU"));
    if (!im.length) return null;
    const r = im[im.length - 1].getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  });
  if (!box) return { ok: false, why: "no cover" };
  await page.mouse.move(box.x, box.y);
  await sleep(700);
  await page.mouse.click(box.x, box.y);
  await sleep(10000);
  const res = await page.evaluate(async () => {
    const vids = [...document.querySelectorAll("video")].filter((v) => v.currentSrc);
    const v = vids.sort((a, b) => b.getBoundingClientRect().width - a.getBoundingClientRect().width)[0];
    if (!v) return { ok: false, n: vids.length };
    const buf = await (await fetch(v.currentSrc)).arrayBuffer();
    const u8 = new Uint8Array(buf);
    let s = "";
    for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
    return { ok: true, src: v.currentSrc, b64: btoa(s) };
  });
  if (!res.ok) return res;
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, Buffer.from(res.b64, "base64"));
  return { ok: true, bytes: fs.statSync(outPath).size, src: res.src.slice(0, 60) };
}

// 账号操作统一从同目录共享模块转出，避免每个任务再复制 acct-switch.mjs。
export { currentAccount, quotaExhausted, switchAccount, switchToFreshAccount, appendLedger, KNOWN_ACCOUNTS }
  from "./acct_switch.mjs";
