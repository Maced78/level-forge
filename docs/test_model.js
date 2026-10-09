// node docs/test_model.js - checks the JavaScript model against frames recorded from the original engine.
const fs = require("fs"), path = require("path");
const Model = require("./model.js");
global.window = {}; eval(fs.readFileSync(path.join(__dirname, "data.js"), "utf8").replace("window.FORGE_DATA", "global.DATA"));
const traces = JSON.parse(fs.readFileSync(path.join(__dirname, "engine_traces.json"), "utf8"));
let frames = 0, bad = 0;
for (const t of traces) {
  const lv = Model.fromDsl(t.dsl), m = new Model(lv.W, lv.H, DATA.nouns);
  let st = lv.state, over = false;
  for (let i = 0; i < t.moves.length; i++) {
    const r = m.step(st, t.moves[i]); st = r.state;
    const got = JSON.stringify(st.map(o => [o.c % lv.W, Math.floor(o.c / lv.W), o.n]).sort());
    const want = t.frames[i + 1], exp = JSON.stringify(want.cells.slice().sort());
    const state = r.won ? "WON" : r.lost ? "LOST" : "PLAYING";
    frames++;
    if (got !== exp || (!over && state !== want.state && !(want.state === "WON" && r.won))) { bad++; if (bad < 4) console.log("MISMATCH at move", i + 1, t.moves.slice(0, i + 1), state, want.state); break; }
    if (r.won || r.lost) break;   // the engine's play state is sticky after the game ends
  }
}
// in-browser solver vs stored optimal solutions
let solved = 0, checked = 0;
for (const g of DATA.gallery.concat(DATA.llm_runs)) {
  if (!g.solution || g.solution.length > 30) continue;
  const lv = Model.fromDsl(g.dsl), m = new Model(lv.W, lv.H, DATA.nouns), r = m.solve(lv.state, 400000);
  checked++; if (r.status === "solved" && r.moves.length === g.solution.length) solved++; else console.log("solver differs:", r.status, r.moves.length, g.solution.length);
}
console.log(`${frames} engine frames compared, ${bad} mismatching traces; JS solver matched the optimal length on ${solved}/${checked} levels`);
process.exit(bad || solved !== checked ? 1 : 0);
