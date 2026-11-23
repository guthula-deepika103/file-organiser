"""
Single-page front-end for the local web app (plain HTML/CSS/JS, no external
resources, so it works offline). All server data is inserted with
``textContent`` - file names are untrusted and must never be parsed as HTML.
"""

from . import __version__

_INDEX = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>File Organizer Assistant</title>
<style>
  :root{--navy:#0e1a35;--blue:#2d4df5;--blue-d:#2339c9;--bg:#f3f5fa;--card:#fff;--line:#e4e8f1;--ink:#16203a;--mut:#6b7794;--ok:#12805c;--warn:#b26a00;--bad:#c0392b;--soft:#eaeefc}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:"Segoe UI",system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif;line-height:1.45}
  .wrap{max-width:1040px;margin:0 auto;padding:24px 20px 60px}
  .hero{background:var(--navy);color:#fff;border-radius:22px;padding:38px 40px;display:flex;justify-content:space-between;align-items:center;gap:24px}
  .eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#8fa2d8;font-weight:700}
  .hero h1{font-size:34px;line-height:1.15;margin:10px 0 8px;max-width:560px}
  .hero p{margin:0;color:#b7c3e6}
  .badge{background:#1b2a52;border-radius:18px;padding:18px 22px;min-width:150px;text-align:center}
  .badge b{display:block;font-size:26px}.badge span{font-size:12px;color:#9fb0de}
  .grid{display:grid;grid-template-columns:1.1fr .9fr;gap:20px;margin-top:20px}
  @media(max-width:820px){.grid{grid-template-columns:1fr}.hero{flex-direction:column;align-items:flex-start}}
  .card{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:26px 28px;margin-top:20px}
  .grid .card{margin-top:0}
  .card.soft{background:var(--soft);border-color:#dbe2fb}
  .step{display:flex;justify-content:space-between;align-items:flex-start}
  .step small{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);font-weight:700}
  .step h2{margin:6px 0 16px;font-size:21px}
  .num{font-size:34px;font-weight:700;color:#dfe4f4}
  label{display:block;font-size:13px;font-weight:600;margin:0 0 6px}
  input[type=text],select{width:100%;padding:13px 14px;border:1px solid var(--line);border-radius:12px;font-size:15px;background:#fff;color:var(--ink)}
  input[type=text]:focus,select:focus{outline:2px solid #b9c5ff;border-color:var(--blue)}
  .row{display:flex;gap:14px;flex-wrap:wrap;margin:14px 0}
  .row>div{flex:1;min-width:180px}
  .check{display:flex;align-items:center;gap:8px;font-size:14px;margin:8px 0;font-weight:500}
  .note{background:#f3f5fa;border-radius:10px;padding:10px 14px;font-size:13px;color:var(--mut);margin:14px 0}
  button{font:inherit;cursor:pointer;border:0;border-radius:12px;padding:13px 22px;font-weight:600;font-size:15px}
  .primary{background:var(--blue);color:#fff}.primary:hover{background:var(--blue-d)}
  .ghost{background:#fff;color:var(--ink);border:1px solid var(--line)}.ghost:hover{background:#f6f7fb}
  .danger{background:#fff;color:var(--bad);border:1px solid #f0c9c4}
  button:disabled{opacity:.5;cursor:not-allowed}
  .actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
  ol.safe{list-style:none;margin:0;padding:0}
  ol.safe li{display:flex;gap:14px;padding:13px 0;border-top:1px solid #d5dcf5}
  ol.safe li:first-child{border-top:0}
  ol.safe i{font-style:normal;font-size:12px;font-weight:700;color:var(--blue);padding-top:2px}
  ol.safe b{display:block}ol.safe span{font-size:13px;color:var(--mut)}
  table{width:100%;border-collapse:collapse;font-size:14px;margin-top:12px}
  th{text-align:left;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);padding:8px 10px;border-bottom:1px solid var(--line)}
  td{padding:9px 10px;border-bottom:1px solid #eef0f6;word-break:break-all}
  .chips{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
  .chip{background:var(--soft);color:var(--blue-d);border-radius:999px;padding:5px 12px;font-size:13px;font-weight:600}
  .pill{border-radius:999px;padding:3px 10px;font-size:12px;font-weight:700}
  .pill.ok{background:#dff5ec;color:var(--ok)}.pill.back{background:#fdeccf;color:var(--warn)}.pill.bad{background:#fbe1dd;color:var(--bad)}
  .op{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:14px 0;border-top:1px solid var(--line)}
  .op:first-child{border-top:0}.op small{color:var(--mut);display:block;word-break:break-all}
  .head{display:flex;justify-content:space-between;align-items:baseline}
  .muted{color:var(--mut);font-size:14px}
  .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:8px 0 14px}
  .stat{background:#f6f8fd;border-radius:14px;padding:14px}.stat b{font-size:22px;display:block}.stat span{font-size:12px;color:var(--mut)}
  .bar{display:flex;align-items:center;gap:10px;margin:6px 0;font-size:13px}
  .bar div.t{flex:1;background:#edf0f8;border-radius:6px;height:10px}.bar div.f{background:var(--blue);height:10px;border-radius:6px}
  .bar span.n{width:150px}.bar span.c{width:40px;text-align:right;color:var(--mut)}
  #toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);padding:13px 20px;border-radius:12px;color:#fff;font-weight:600;display:none;max-width:90%;z-index:9}
  #toast.ok{background:var(--ok)}#toast.err{background:var(--bad)}#toast.info{background:var(--navy)}
  .hidden{display:none}
  footer{display:flex;justify-content:space-between;color:#97a1ba;font-size:11px;letter-spacing:.12em;text-transform:uppercase;margin-top:28px}
</style>
</head>
<body>
<div class="wrap">

  <section class="hero">
    <div>
      <div class="eyebrow">File Organizer Assistant</div>
      <h1>A calmer way to organize your digital workspace.</h1>
      <p>Preview first. Organize safely. Roll back when needed.</p>
    </div>
    <div class="badge"><b id="heroFiles">0</b><span>files organized so far</span></div>
  </section>

  <div class="grid">
    <section class="card">
      <div class="step"><div><small>01 / Select source</small><h2>Choose a folder</h2></div><div class="num">01</div></div>
      <label for="path">Folder path</label>
      <input type="text" id="path" placeholder="C:\Users\YourName\Downloads" autocomplete="off" spellcheck="false">
      <div class="row">
        <div><label for="strategy">Group files by</label>
          <select id="strategy">
            <option value="type">File type (Documents, Images...)</option>
            <option value="date">Last modified month (2026-11)</option>
            <option value="size">Size (small / medium / large)</option>
          </select></div>
      </div>
      <label class="check"><input type="checkbox" id="recursive"> Include subfolders</label>
      <label class="check"><input type="checkbox" id="atomic"> All-or-nothing (undo everything if any file fails)</label>
      <div class="note">Your files stay on this computer. A preview is generated before any move.</div>
      <div class="actions">
        <button class="primary" id="btnPreview">Generate preview &rarr;</button>
        <button class="ghost" id="btnDupes">Find duplicates</button>
      </div>
    </section>

    <aside class="card soft">
      <div class="eyebrow" style="color:#6c7cc9">Built for control</div>
      <h2 style="margin:6px 0 10px;font-size:23px">Safe by design.</h2>
      <ol class="safe">
        <li><i>01</i><div><b>Dry-run preview</b><span>See every planned category before changes.</span></div></li>
        <li><i>02</i><div><b>Collision protection</b><span>Existing files are never silently overwritten.</span></div></li>
        <li><i>03</i><div><b>Rollback history</b><span>Restore files from completed operations.</span></div></li>
        <li><i>04</i><div><b>Crash-safe moves</b><span>A journal restores files if the app is interrupted.</span></div></li>
        <li><i>05</i><div><b>Audit trail</b><span>Every file operation is recorded.</span></div></li>
      </ol>
    </aside>
  </div>

  <section class="card hidden" id="previewCard">
    <div class="step"><div><small>02 / Review</small><h2>Preview</h2></div><div class="num">02</div></div>
    <div class="note hidden" id="recoverNote">A previous run in this folder did not finish.
      <button class="ghost" id="btnRecover" style="padding:6px 12px;margin-left:8px">Restore those files</button></div>
    <div id="previewSummary" class="muted"></div>
    <div class="chips" id="previewChips"></div>
    <div style="overflow-x:auto"><table id="previewTable"><thead><tr><th>File</th><th>Category</th><th>Size</th><th>Will be moved to</th></tr></thead><tbody></tbody></table></div>
    <div class="muted" id="previewMore"></div>
    <div class="actions" style="margin-top:18px">
      <button class="primary" id="btnOrganize">Organize these files</button>
      <button class="ghost" id="btnCancel">Cancel</button>
    </div>
  </section>

  <section class="card hidden" id="dupeCard">
    <div class="step"><div><small>Extra / Duplicates</small><h2>Duplicate files</h2></div></div>
    <div id="dupeSummary" class="muted"></div>
    <div id="dupeList"></div>
    <div class="actions" style="margin-top:16px">
      <button class="primary" id="btnQuarantine">Move extra copies to "Duplicates"</button>
      <button class="ghost" id="btnDupeClose">Close</button>
    </div>
  </section>

  <section class="card">
    <div class="head"><div><div class="eyebrow" style="color:var(--mut)">Activity</div><h2 style="margin:6px 0 0;font-size:21px">Recent operations</h2></div>
      <span class="muted" id="opCount">0 shown</span></div>
    <div id="ops" style="margin-top:8px"><div class="muted" style="padding:14px 0">No activity yet. Generate your first preview to get started.</div></div>
  </section>

  <section class="card">
    <div class="head"><div><div class="eyebrow" style="color:var(--mut)">Insights</div><h2 style="margin:6px 0 0;font-size:21px">Analytics</h2></div>
      <button class="ghost" id="btnReport">Download report (.md)</button></div>
    <div class="stats" id="stats"></div>
    <div id="bars"></div>
  </section>

  <footer><span>File Organizer Assistant v__VERSION__</span><span>Local-first &middot; Python powered</span></footer>
</div>
<div id="toast"></div>

<script>
(function(){
  var TOKEN = "__TOKEN__";
  var $ = function(id){return document.getElementById(id);};
  var busy = false;

  function toast(msg, kind){
    var t = $("toast"); t.textContent = msg; t.className = kind || "info"; t.style.display = "block";
    clearTimeout(toast._t); toast._t = setTimeout(function(){t.style.display = "none";}, 5200);
  }
  function fmtSize(n){
    var u = ["B","KB","MB","GB"], i = 0;
    while(n >= 1024 && i < 3){n /= 1024; i++;}
    return (i === 0 ? n.toFixed(0) : n.toFixed(1)) + " " + u[i];
  }
  function el(tag, text, cls){
    var e = document.createElement(tag);
    if(text !== undefined && text !== null) e.textContent = text;
    if(cls) e.className = cls;
    return e;
  }
  function api(method, url, body){
    var opts = {method: method, headers: {"X-Organizer-Token": TOKEN}};
    if(body !== undefined){opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body);}
    return fetch(url, opts).then(function(r){
      return r.json().catch(function(){return {error: "Unexpected response"};}).then(function(j){
        if(!r.ok) throw new Error(j.error || ("Request failed (" + r.status + ")"));
        return j;
      });
    });
  }
  function form(){
    return {path: $("path").value.trim(), strategy: $("strategy").value,
            recursive: $("recursive").checked, atomic: $("atomic").checked};
  }
  function setBusy(b){
    busy = b;
    ["btnPreview","btnDupes","btnOrganize","btnQuarantine"].forEach(function(id){$(id).disabled = b;});
  }
  function run(promise, okFn){
    if(busy) return;
    setBusy(true);
    promise().then(okFn).catch(function(e){toast(e.message, "err");}).then(function(){setBusy(false);});
  }

  // ---- preview -------------------------------------------------------------
  function showPreview(d){
    $("dupeCard").classList.add("hidden");
    $("previewCard").classList.remove("hidden");
    $("recoverNote").classList.toggle("hidden", !d.pending_recovery);
    var tb = $("previewTable").tBodies[0]; tb.textContent = "";
    if(d.total_files === 0){
      $("previewSummary").textContent = "No organize-able files were found in this folder.";
      $("previewChips").textContent = ""; $("previewMore").textContent = "";
      $("btnOrganize").disabled = true; return;
    }
    $("btnOrganize").disabled = false;
    $("previewSummary").textContent = d.total_files + " files (" + fmtSize(d.total_bytes) + ") in " + d.target;
    var chips = $("previewChips"); chips.textContent = "";
    Object.keys(d.by_category).sort(function(a,b){return d.by_category[b]-d.by_category[a];}).forEach(function(k){
      chips.appendChild(el("span", k + ": " + d.by_category[k], "chip"));
    });
    d.rows.forEach(function(r){
      var tr = document.createElement("tr");
      tr.appendChild(el("td", r.filename)); tr.appendChild(el("td", r.category));
      tr.appendChild(el("td", fmtSize(r.size_bytes)));
      tr.appendChild(el("td", r.destination + (r.renamed ? "  (renamed: name already taken)" : "")));
      tb.appendChild(tr);
    });
    $("previewMore").textContent = d.truncated ? "Showing the first " + d.rows.length + " of " + d.total_files + " files." : "";
    $("previewCard").scrollIntoView({behavior: "smooth", block: "start"});
  }
  $("btnPreview").addEventListener("click", function(){
    var f = form();
    run(function(){return api("POST", "/api/preview", f);}, showPreview);
  });
  $("btnCancel").addEventListener("click", function(){$("previewCard").classList.add("hidden"); toast("Cancelled. No files were changed.", "info");});
  $("btnOrganize").addEventListener("click", function(){
    var f = form();
    run(function(){return api("POST", "/api/organize", f);}, function(r){
      $("previewCard").classList.add("hidden");
      if(r.aborted) toast("Stopped on the first error and reverted everything (" + r.failed + " failure). No files were left half-moved.", "err");
      else if(r.failed) toast("Organized " + r.successful + " files, " + r.failed + " failed. " + (r.errors[0] || ""), "err");
      else toast("Organized " + r.successful + " files. Operation " + r.operation_id + " saved - you can undo it below.", "ok");
      refresh();
    });
  });
  $("btnRecover").addEventListener("click", function(){
    var f = form();
    run(function(){return api("POST", "/api/recover", {path: f.path});}, function(r){
      toast("Restored " + r.restored + " files from the interrupted run.", "ok");
      $("recoverNote").classList.add("hidden");
    });
  });

  // ---- duplicates ----------------------------------------------------------
  $("btnDupes").addEventListener("click", function(){
    var f = form();
    run(function(){return api("POST", "/api/duplicates/scan", f);}, function(d){
      $("previewCard").classList.add("hidden");
      $("dupeCard").classList.remove("hidden");
      var list = $("dupeList"); list.textContent = "";
      if(d.total_groups === 0){
        $("dupeSummary").textContent = "No duplicate files found.";
        $("btnQuarantine").disabled = true; return;
      }
      $("btnQuarantine").disabled = false;
      $("dupeSummary").textContent = d.total_groups + " duplicate groups, " + d.total_extra_copies +
        " extra copies wasting " + fmtSize(d.wasted_bytes) + ". The oldest copy of each stays where it is.";
      d.groups.forEach(function(g){
        var box = el("div", null, "op"); var left = el("div");
        left.appendChild(el("b", "Keep: " + g.keep));
        g.extras.forEach(function(x){left.appendChild(el("small", "Move: " + x));});
        box.appendChild(left); list.appendChild(box);
      });
      $("dupeCard").scrollIntoView({behavior: "smooth", block: "start"});
    });
  });
  $("btnDupeClose").addEventListener("click", function(){$("dupeCard").classList.add("hidden");});
  $("btnQuarantine").addEventListener("click", function(){
    var f = form();
    run(function(){return api("POST", "/api/duplicates/quarantine", f);}, function(r){
      $("dupeCard").classList.add("hidden");
      toast("Moved " + r.successful + " duplicate copies into the Duplicates folder. Undo is available below.", "ok");
      refresh();
    });
  });

  // ---- history / undo ------------------------------------------------------
  function renderOps(list){
    var box = $("ops"); box.textContent = "";
    $("opCount").textContent = list.length + " shown";
    if(!list.length){box.appendChild(el("div", "No activity yet. Generate your first preview to get started.", "muted")); return;}
    list.forEach(function(op){
      var row = el("div", null, "op"); var left = el("div");
      var title = el("b", op.operation_id + "  ");
      var pill = el("span", op.rolled_back ? "Rolled back" : (op.failed ? "Completed with errors" : "Completed"),
                    "pill " + (op.rolled_back ? "back" : (op.failed ? "bad" : "ok")));
      title.appendChild(pill); left.appendChild(title);
      left.appendChild(el("small", (op.timestamp || "").replace("T", " ").slice(0, 19) + "  |  " + op.files + " files  |  by " + op.strategy));
      left.appendChild(el("small", op.target_directory));
      row.appendChild(left);
      if(op.can_undo){
        var b = el("button", "Undo", "danger");
        b.addEventListener("click", function(){
          if(!window.confirm("Restore the files of " + op.operation_id + " to their original locations?")) return;
          run(function(){return api("POST", "/api/undo", {operation_id: op.operation_id});}, function(r){
            toast("Restored " + r.restored + " files" + (r.failed ? " (" + r.failed + " problems: " + (r.errors[0] || "") + ")" : "."), r.failed ? "err" : "ok");
            refresh();
          });
        });
        row.appendChild(b);
      }
      box.appendChild(row);
    });
  }
  function renderStats(s){
    $("heroFiles").textContent = s.total_files_organized;
    var st = $("stats"); st.textContent = "";
    [["Operations", s.total_operations], ["Files organized", s.total_files_organized],
     ["Data managed", s.total_volume_mb + " MB"], ["Rolled back", s.status_breakdown.ROLLED_BACK]].forEach(function(p){
      var c = el("div", null, "stat"); c.appendChild(el("b", String(p[1]))); c.appendChild(el("span", p[0])); st.appendChild(c);
    });
    var bars = $("bars"); bars.textContent = "";
    var dist = s.category_distribution, keys = Object.keys(dist), max = 1;
    keys.forEach(function(k){max = Math.max(max, dist[k]);});
    keys.sort(function(a,b){return dist[b]-dist[a];}).forEach(function(k){
      var r = el("div", null, "bar"); r.appendChild(el("span", k, "n"));
      var t = el("div", null, "t"); var f = el("div", null, "f"); f.style.width = (dist[k] / max * 100) + "%"; t.appendChild(f);
      r.appendChild(t); r.appendChild(el("span", String(dist[k]), "c")); bars.appendChild(r);
    });
  }
  function refresh(){
    api("GET", "/api/operations").then(function(d){renderOps(d.operations);}).catch(function(e){toast(e.message, "err");});
    api("GET", "/api/stats").then(renderStats).catch(function(){});
  }
  $("btnReport").addEventListener("click", function(){
    fetch("/api/report", {headers: {"X-Organizer-Token": TOKEN}}).then(function(r){return r.blob();}).then(function(b){
      var a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = "organizer_report.md";
      document.body.appendChild(a); a.click(); a.remove();
    });
  });
  $("path").addEventListener("keydown", function(e){if(e.key === "Enter") $("btnPreview").click();});
  refresh();
})();
</script>
</body>
</html>
"""


def render_index(token: str) -> str:
    """Returns the page with the per-run session token and version filled in."""
    return _INDEX.replace("__TOKEN__", token).replace("__VERSION__", __version__)
