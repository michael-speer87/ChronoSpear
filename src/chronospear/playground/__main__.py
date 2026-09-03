"""Launch the local CAM visual playground."""

# ruff: noqa: E501 -- Embedded HTML is kept readable as browser source.

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from chronospear.playground import PlaygroundAdapter, build_demo_world
from chronospear.world_import import import_world

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ChronoSpear CAM Playground</title>
<style>
:root { color-scheme: dark; --green:#66d19e; --blue:#72b7ff; --ink:#e8eef5;
  --muted:#99a8b8; --panel:#18212b; --edge:#304050; }
* { box-sizing:border-box } body { margin:0; background:#0d131a; color:var(--ink);
  font:16px/1.5 ui-sans-serif,system-ui,sans-serif; }
main { max-width:920px; margin:auto; padding:36px 20px 64px; }
h1 { margin:0; font-size:clamp(1.7rem,5vw,2.5rem); } .intro { color:var(--muted); margin:.3rem 0 2rem; }
.selectors { display:grid; grid-template-columns:1fr 2fr; gap:16px; margin-bottom:20px; }
label { color:var(--muted); font-size:.78rem; font-weight:700; letter-spacing:.09em;
  text-transform:uppercase; } select { display:block; width:100%; margin-top:7px; padding:11px;
  border:1px solid var(--edge); border-radius:8px; background:var(--panel); color:var(--ink); font:inherit; }
.card { border:1px solid var(--edge); border-top:4px solid var(--green); border-radius:10px;
  background:var(--panel); padding:24px; box-shadow:0 14px 36px #0005; }
.card.occurrence { border-top-color:var(--blue); } .eyebrow { color:var(--green); font-size:.75rem;
  font-weight:800; letter-spacing:.12em; text-transform:uppercase; } .occurrence .eyebrow { color:var(--blue); }
h2 { margin:.2rem 0 1.3rem; } dl { display:grid; grid-template-columns:minmax(120px,180px) 1fr;
  margin:0; } dt,dd { padding:9px 0; border-bottom:1px solid var(--edge); } dt { color:var(--muted); }
dd { margin:0; overflow-wrap:anywhere; } .connections { display:grid; grid-template-columns:repeat(2,1fr);
  gap:15px; margin-top:24px; } section { border:1px solid var(--edge); border-radius:8px; padding:14px; }
h3 { margin:0 0 10px; color:var(--muted); font-size:.78rem; text-transform:uppercase;
  letter-spacing:.06em; } button { display:block; width:100%; padding:10px; margin-top:8px; text-align:left;
  border:1px solid #397357; border-radius:7px; background:#173526; color:var(--ink); cursor:pointer; }
button.history { border-color:#315f8c; background:#132d47; } button:hover { filter:brightness(1.25); }
.empty { color:var(--muted); font-style:italic; font-size:.9rem; }
@media (max-width:620px) { .selectors,.connections { grid-template-columns:1fr; } dl { display:block; }
  dt { border:0; padding-bottom:0; } dd { padding-top:2px; } }
</style>
</head>
<body><main>
<h1>CAM Visual Playground</h1>
<p class="intro">A read-only window into the current Chrono Associative Memory foundation.</p>
<div class="selectors">
  <label>Object Type<select id="type">
    <option value="identity">Identity</option><option value="association">Association</option>
    <option value="occurrence">Historical Occurrence</option>
  </select></label>
  <label>Object<select id="object"></select></label>
</div>
<article class="card" id="card"><div id="detail"></div></article>
</main>
<script>
let world;
const typeSelect=document.querySelector('#type'), objectSelect=document.querySelector('#object');
const card=document.querySelector('#card'), detail=document.querySelector('#detail');
const escapeHtml=value=>String(value).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
function populate(preferred) {
  objectSelect.innerHTML=world.objects[typeSelect.value].map(o=>
    `<option value="${escapeHtml(o.id)}">${escapeHtml(o.label)}</option>`).join('');
  if(preferred) objectSelect.value=preferred;
  render();
}
function render() {
  const item=world.details.find(o=>o.type===typeSelect.value&&o.id===objectSelect.value);
  if(!item) return;
  card.className=`card ${item.type}`;
  const fields=item.fields.map(([name,value])=>`<dt>${escapeHtml(name)}</dt><dd>${escapeHtml(value)||'—'}</dd>`).join('');
  const groups=item.groups.map(([name,refs])=>`<section><h3>${escapeHtml(name)}</h3>${refs.length?
    refs.map(ref=>`<button class="${ref.type==='occurrence'?'history':''}" data-type="${ref.type}" data-id="${escapeHtml(ref.id)}">Open ${escapeHtml(ref.label)}</button>`).join(''):
    '<span class="empty">None</span>'}</section>`).join('');
  const names={identity:'Identity',association:'Association',occurrence:'Historical Occurrence'};
  detail.innerHTML=`<div class="eyebrow">${names[item.type]}</div><h2>${escapeHtml(item.label)}</h2><dl>${fields}</dl><div class="connections">${groups}</div>`;
}
typeSelect.addEventListener('change',()=>populate()); objectSelect.addEventListener('change',render);
detail.addEventListener('click',event=>{ const button=event.target.closest('button[data-type]'); if(!button)return;
  typeSelect.value=button.dataset.type; populate(button.dataset.id); });
fetch('/api/world').then(response=>{if(!response.ok)throw Error('Could not load demo world');return response.json()})
  .then(data=>{world=data;populate(world.objects.identity[0].id)})
  .catch(error=>{detail.textContent=error.message});
</script></body></html>"""


def _handler(snapshot: bytes) -> type[BaseHTTPRequestHandler]:
    class PlaygroundHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                self._respond(_PAGE.encode(), "text/html; charset=utf-8")
            elif self.path == "/api/world":
                self._respond(snapshot, "application/json; charset=utf-8")
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def _respond(self, body: bytes, content_type: str) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return PlaygroundHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the read-only CAM visual playground.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument(
        "--world",
        type=Path,
        help="directory containing memory.json and optional catalog.json",
    )
    args = parser.parse_args()
    world = import_world(args.world) if args.world is not None else build_demo_world()
    snapshot = json.dumps(PlaygroundAdapter(world).snapshot()).encode()
    server = ThreadingHTTPServer((args.host, args.port), _handler(snapshot))
    print(
        f"ChronoSpear CAM Playground: http://{args.host}:{server.server_port}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
        raise SystemExit(0) from None


if __name__ == "__main__":
    main()
