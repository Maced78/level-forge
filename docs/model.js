// model.js - JavaScript port of blueprints/baba_is_auto/solver/model.hpp (itself a model of
// Game::MovePlayer in the original baba-is-auto engine). Subset: ordinary nouns, IS, and the
// properties YOU / STOP / PUSH / WIN / SINK / DEFEAT, plus noun transformations.
// docs/test_model.js replays thousands of frames recorded from the ORIGINAL engine against it.
(function (root) {
  const PROPS = { YOU: 1, STOP: 2, PUSH: 4, WIN: 8, SINK: 16, DEFEAT: 32 };
  const DX = { U: 0, D: 0, L: -1, R: 1 }, DY = { U: -1, D: 1, L: 0, R: 0 };
  const isText = n => !n.startsWith("ICON_");

  function Model(W, H, nouns) {
    this.W = W; this.H = H; this.nouns = new Set(nouns);
  }

  // state: array of {c: cellIndex, n: name}
  Model.prototype.parse = function (objs) {
    const W = this.W, H = this.H, text = new Array(W * H).fill(null);
    for (const o of objs) if (isText(o.n)) text[o.c] = o.n;
    const props = {}, xf = [], list = [];
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const a = text[y * W + x];
      if (!a || !this.nouns.has(a)) continue;
      for (let d = 0; d < 2; d++) {
        const dx = d === 0 ? 1 : 0, dy = d === 1 ? 1 : 0;
        if (x + 2 * dx >= W || y + 2 * dy >= H) continue;
        const b = text[(y + dy) * W + x + dx], c = text[(y + 2 * dy) * W + x + 2 * dx];
        if (b !== "IS" || !c) continue;
        if (this.nouns.has(c)) { xf.push(["ICON_" + a, "ICON_" + c]); list.push(a + " IS " + c); }
        else if (c !== "IS") { if (PROPS[c]) props["ICON_" + a] = (props["ICON_" + a] || 0) | PROPS[c]; list.push(a + " IS " + c); }
      }
    }
    return { props, xf, list };
  };

  Model.prototype.dest = function (cell, dir) {
    const x = cell % this.W + DX[dir], y = Math.floor(cell / this.W) + DY[dir];
    return (x < 0 || x >= this.W || y < 0 || y >= this.H) ? -1 : y * this.W + x;
  };

  Model.prototype.canMove = function (objs, r, cell, dir) {
    const d = this.dest(cell, dir);
    if (d < 0) return false;
    let anyPush = false;
    for (const o of objs) {
      if (o.c !== d) continue;
      const p = r.props[o.n] || 0;
      if (!isText(o.n) && (p & 2) && !(p & 4)) return false;
      if (isText(o.n) || (p & 4)) anyPush = true;
    }
    return !(anyPush && !this.canMove(objs, r, d, dir));
  };

  Model.prototype.processMove = function (objs, r, cell, dir, moving, flags) {
    const d = this.dest(cell, dir), pushed = [];
    for (let i = 0; i < objs.length; i++)
      if (objs[i].c === d && (isText(objs[i].n) || ((r.props[objs[i].n] || 0) & 4))) pushed.push(i);
    if (pushed.length && this.canMove(objs, r, d, dir)) {
      for (const i of pushed) if (isText(objs[i].n)) flags.text = true;
      this.processMove(objs, r, d, dir, pushed, flags);
    }
    for (const i of moving) objs[i].c = d;
  };

  Model.prototype.step = function (state, dir) {
    const W = this.W;
    let objs = state.map(o => ({ c: o.c, n: o.n, id: o.id }));
    const rules = this.parse(objs), flags = { text: false };
    const you = o => (rules.props[o.n] || 0) & 1;
    const stacks = [];
    for (const o of objs) if (you(o) && !stacks.includes(o.c)) stacks.push(o.c);
    const col = c => c % W, row = c => Math.floor(c / W);
    stacks.sort((l, r) => dir === "L" ? (col(l) - col(r) || l - r) : dir === "R" ? (col(r) - col(l) || l - r)
      : dir === "U" ? (row(l) - row(r) || l - r) : (row(r) - row(l) || l - r));
    const ids = stacks.map(s => objs.map((o, i) => (o.c === s && you(o)) ? i : -1).filter(i => i >= 0));
    stacks.forEach((s, k) => {
      const movable = ids[k].filter(i => objs[i].c === s);
      if (movable.length && this.canMove(objs, rules, s, dir)) this.processMove(objs, rules, s, dir, movable, flags);
    });
    let r2 = flags.text ? this.parse(objs) : rules;
    if (r2.xf.length) {
      const n = objs.length;
      for (let i = 0; i < n; i++) {
        const targets = r2.xf.filter(x => x[0] === objs[i].n).map(x => x[1]);
        if (!targets.length || targets.includes(objs[i].n)) continue;
        objs[i].n = targets[0];
        for (let t = 1; t < targets.length; t++) objs.push({ c: objs[i].c, n: targets[t] });
      }
      r2 = this.parse(objs);
    }
    const P = o => r2.props[o.n] || 0, count = {}, sink = {}, defeat = {}, win = {};
    for (const o of objs) { count[o.c] = (count[o.c] || 0) + 1; if (P(o) & 16) sink[o.c] = true; }
    objs = objs.filter(o => !(sink[o.c] && count[o.c] >= 2));
    for (const o of objs) if (P(o) & 32) defeat[o.c] = true;
    objs = objs.filter(o => !(defeat[o.c] && (P(o) & 1)));
    for (const o of objs) if (P(o) & 8) win[o.c] = true;
    let hasPlayer = false, won = false;
    for (const o of objs) if (P(o) & 1) { hasPlayer = true; if (win[o.c]) won = true; }
    return { state: objs, won, lost: !won && !hasPlayer, rules: this.parse(objs).list };
  };

  Model.key = state => state.map(o => o.c * 512 + "|" + o.n).sort().join(",");

  // Breadth-first search: shortest solution or proof that none exists (within the bound).
  Model.prototype.solve = function (start, maxStates) {
    maxStates = maxStates || 150000;
    const seen = new Map([[Model.key(start), 0]]), nodes = [{ p: -1, m: "" }];
    let frontier = [[0, start]], explored = 1;
    while (frontier.length) {
      const next = [];
      for (const [idx, st] of frontier) {
        for (const m of "UDLR") {
          const r = this.step(st, m);
          if (r.won) { let s = m, n = idx; while (nodes[n].p >= 0) { s = nodes[n].m + s; n = nodes[n].p; } return { status: "solved", moves: s, states: explored }; }
          if (r.lost) continue;
          const k = Model.key(r.state);
          if (seen.has(k)) continue;
          seen.set(k, nodes.length); nodes.push({ p: idx, m }); next.push([nodes.length - 1, r.state]);
          if (++explored >= maxStates) return { status: "unknown", moves: "", states: explored };
        }
      }
      frontier = next;
    }
    return { status: "unsolvable", moves: "", states: explored };
  };

  // "BABA IS YOU . ." rows -> {W, H, state}
  Model.fromDsl = function (text, known) {
    const rows = text.trim().split(/\n+/).map(r => r.trim().split(/\s+/));
    const W = rows[0].length;
    if (rows.some(r => r.length !== W)) throw new Error("rows have different lengths: " + rows.map(r => r.length).join(", "));
    const state = [];
    rows.forEach((row, y) => row.forEach((cell, x) => {
      if (cell === "." || cell === "_") return;
      for (const tok of cell.split("+")) {
        const n = tok === tok.toUpperCase() ? tok : "ICON_" + tok.toUpperCase();
        if (known && !known.has(n)) throw new Error("unknown entity '" + tok + "' at column " + (x + 1) + ", row " + (y + 1));
        state.push({ c: y * W + x, n });
      }
    }));
    return { W, H: rows.length, state };
  };

  root.ForgeModel = Model;
  if (typeof module !== "undefined") module.exports = Model;
})(typeof window !== "undefined" ? window : globalThis);
