"""Launch the local ChronoSpear World Builder."""

# ruff: noqa: E501 -- Embedded HTML is intentionally readable as browser source.

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast

from chronospear.cam import RelationshipVocabulary
from chronospear.world_builder import MemoryJsonSerializer
from chronospear.world_import import validate_memory_document

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ChronoSpear World Builder</title><style>
:root{color-scheme:dark;--bg:#0d131a;--panel:#18212b;--edge:#304050;--ink:#e8eef5;--muted:#9cadbd;--green:#66d19e;--blue:#72b7ff;--danger:#ff8585}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:28px 20px 70px}
header{display:flex;gap:18px;align-items:end;justify-content:space-between;flex-wrap:wrap}h1{margin:0}.world{color:var(--muted);overflow-wrap:anywhere}.toolbar{display:flex;gap:10px;align-items:center}button{border:1px solid #397357;border-radius:7px;background:#173526;color:var(--ink);padding:9px 13px;cursor:pointer}button:hover{filter:brightness(1.2)}button.danger{border-color:#743d45;background:#351b20}#status{font-weight:700}.saved{color:var(--green)}.dirty{color:#ffd36a}.error{color:var(--danger)}
.warning{border-left:3px solid #ffd36a;padding:9px 12px;background:#2b2718;margin:18px 0;color:#e9dca9}.tabs{display:flex;gap:8px;margin:20px 0}.tabs button.active{background:#285f45}.page{display:none}.page.active{display:grid;grid-template-columns:1.1fr 1fr;gap:20px}
.panel{background:var(--panel);border:1px solid var(--edge);border-radius:9px;padding:18px}h2{margin-top:0}.item{border-bottom:1px solid var(--edge);padding:12px 0;display:flex;justify-content:space-between;gap:12px}.item:last-child{border:0}.summary{overflow-wrap:anywhere}.actions{display:flex;gap:7px;align-items:start}
form{display:grid;gap:12px}label{color:var(--muted);font-size:.8rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase}input,select,textarea{display:block;width:100%;margin-top:5px;padding:9px;border:1px solid var(--edge);border-radius:6px;background:#101820;color:var(--ink);font:inherit}textarea{min-height:90px;resize:vertical}.large{min-height:190px}select[multiple]{min-height:115px}.form-actions{display:flex;gap:8px}.empty{color:var(--muted);font-style:italic}
@media(max-width:760px){.page.active{grid-template-columns:1fr}.tabs{overflow-x:auto}}
</style></head><body><main>
<header><div><h1>ChronoSpear World Builder</h1><div class="world" id="world-path"></div></div><div class="toolbar"><span id="status" class="saved">Saved</span><button id="save">Save memory.json</button></div></header>
<div class="warning">Package keys are stable authoring references. Changing a previously saved key may create a new canonical identity on the next import. This tool never changes catalog.json.</div>
<nav class="tabs"><button data-tab="identities" class="active">Identities</button><button data-tab="associations">Associations</button><button data-tab="occurrences">Historical Occurrences</button></nav>
<section id="identities" class="page active"><div class="panel"><h2>Identities</h2><button onclick="newIdentity()">Add Identity</button><div id="identity-list"></div></div><div class="panel"><h2>Identity Editor</h2><form id="identity-form"><input type="hidden" name="index"><label>Kind<select name="kind"><option>ENTITY</option><option>PLACE</option><option>DESCRIBER</option></select></label><label>Key<input name="key" required></label><label>Name<input name="name"></label><label>Synopsis<textarea name="synopsis"></textarea></label><label>Description<textarea class="large" name="description"></textarea></label><div class="form-actions"><button type="submit">Apply</button><button type="button" onclick="newIdentity()">Clear</button></div></form></div></section>
<section id="associations" class="page"><div class="panel"><h2>Associations</h2><button onclick="newAssociation()">Add Association</button><div id="association-list"></div></div><div class="panel"><h2>Association Editor</h2><form id="association-form"><input type="hidden" name="index"><label>Key<input name="key" required></label><label>Source<select name="source" required></select></label><label>Relationship<select name="relationship" required></select></label><label>Target<select name="target" required></select></label><div class="form-actions"><button type="submit">Apply</button><button type="button" onclick="newAssociation()">Clear</button></div></form></div></section>
<section id="occurrences" class="page"><div class="panel"><h2>Historical Occurrences</h2><button onclick="newOccurrence()">Add Occurrence</button><div id="occurrence-list"></div></div><div class="panel"><h2>Historical Occurrence Editor</h2><form id="occurrence-form"><input type="hidden" name="index"><label>Key<input name="key" required></label><label>Participants<select name="participants" multiple required></select></label><label>Place<select name="place" required></select></label><label>WorldTime<input name="world_time" type="number" min="0" required></label><label>SystemTime<input name="system_time" type="number" min="0" required></label><label>Synopsis<textarea name="synopsis" required></textarea></label><label>Story<textarea class="large" name="story" required></textarea></label><label>Started Associations<select name="started_associations" multiple></select></label><label>Ended Associations<select name="ended_associations" multiple></select></label><div class="form-actions"><button type="submit">Apply</button><button type="button" onclick="newOccurrence()">Clear</button></div></form></div></section>
</main><script>
let world={identities:[],associations:[],historical_occurrences:[]},relationships=[];
const $=selector=>document.querySelector(selector), esc=value=>String(value).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const identityName=key=>{const item=world.identities.find(x=>x.key===key);return item?`${item.name||'(unnamed)'} (${item.key})`:`Missing (${key})`};
const associationName=item=>`${item.key} — ${identityName(item.source)} ${item.relationship} ${identityName(item.target)}`;
function dirty(){const status=$('#status');status.textContent='Unsaved changes';status.className='dirty'}
function setOptions(select,items,label,selected=[]){select.innerHTML=items.map(item=>`<option value="${esc(item.key)}" ${selected.includes(item.key)?'selected':''}>${esc(label(item))}</option>`).join('')}
function nextKey(prefix,items){let n=1;const used=new Set(items.map(x=>x.key));while(used.has(prefix+n))n++;return prefix+n}
function render(){
  $('#identity-list').innerHTML=world.identities.length?world.identities.map((x,i)=>`<div class="item"><div class="summary"><b>${esc(x.key)}</b> &nbsp; ${esc(x.kind)} &nbsp; ${esc(x.name||'(unnamed)')}</div><div class="actions"><button onclick="editIdentity(${i})">Edit</button><button class="danger" onclick="removeItem('identities',${i})">Delete</button></div></div>`).join(''):'<p class="empty">No identities yet.</p>';
  $('#association-list').innerHTML=world.associations.length?world.associations.map((x,i)=>`<div class="item"><div class="summary">${esc(associationName(x))}</div><div class="actions"><button onclick="editAssociation(${i})">Edit</button><button class="danger" onclick="removeItem('associations',${i})">Delete</button></div></div>`).join(''):'<p class="empty">No associations yet.</p>';
  $('#occurrence-list').innerHTML=world.historical_occurrences.length?world.historical_occurrences.map((x,i)=>`<div class="item"><div class="summary"><b>${esc(x.key)}</b> | WT ${x.world_time} | ${esc(x.synopsis)}</div><div class="actions"><button onclick="editOccurrence(${i})">Edit</button><button class="danger" onclick="removeItem('historical_occurrences',${i})">Delete</button></div></div>`).join(''):'<p class="empty">No occurrences yet.</p>';
  refreshSelectors();
}
function refreshSelectors(){
  const af=$('#association-form'),of=$('#occurrence-form'),all=world.identities;
  const identityLabel=x=>identityName(x.key);setOptions(af.source,all,identityLabel);setOptions(af.target,all,identityLabel);
  af.relationship.innerHTML=relationships.map(x=>`<option>${esc(x)}</option>`).join('');
  setOptions(of.participants,all.filter(x=>x.kind==='ENTITY'),identityLabel);
  setOptions(of.place,all.filter(x=>x.kind==='PLACE'),identityLabel);
  const assocLabel=x=>associationName(x);setOptions(of.started_associations,world.associations,assocLabel);setOptions(of.ended_associations,world.associations,assocLabel);
}
function removeItem(family,index){world[family].splice(index,1);dirty();render()}
function fill(form,item,index){form.reset();form.index.value=index;Object.entries(item).forEach(([key,value])=>{const input=form.elements.namedItem(key);if(!input)return;if(input.multiple)[...input.options].forEach(o=>o.selected=value.includes(o.value));else input.value=value})}
function newIdentity(kind='ENTITY'){const f=$('#identity-form');f.reset();f.kind.value=kind;f.index.value='';f.key.value=nextKey(kind==='ENTITY'?'e':kind==='PLACE'?'p':'d',world.identities)}
function editIdentity(i){fill($('#identity-form'),world.identities[i],i)}
function newAssociation(){const f=$('#association-form');f.reset();f.index.value='';f.key.value=nextKey('a',world.associations)}
function editAssociation(i){refreshSelectors();fill($('#association-form'),world.associations[i],i)}
function newOccurrence(){const f=$('#occurrence-form');f.reset();f.index.value='';f.key.value=nextKey('ho',world.historical_occurrences);f.world_time.value=0;f.system_time.value=0}
function editOccurrence(i){refreshSelectors();fill($('#occurrence-form'),world.historical_occurrences[i],i)}
async function validateCandidate(candidate){const response=await fetch('/api/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(candidate)});const result=await response.json();if(!response.ok)throw Error(result.error)}
function apply(form,family,transform,reset){
  form.addEventListener('invalid',()=>{const status=$('#status');status.textContent='Cannot apply: correct the highlighted form field.';status.className='error'},true);
  form.addEventListener('submit',async event=>{event.preventDefault();const data=new FormData(form),item=transform(data),index=form.index.value,candidate=JSON.parse(JSON.stringify(world));if(index==='')candidate[family].push(item);else candidate[family][Number(index)]=item;try{await validateCandidate(candidate)}catch(error){const status=$('#status');status.textContent='Cannot apply: '+error.message;status.className='error';return}world=candidate;dirty();render();reset(item)})
}
apply($('#identity-form'),'identities',d=>({key:d.get('key'),kind:d.get('kind'),name:d.get('name'),synopsis:d.get('synopsis'),description:d.get('description')}),item=>newIdentity(item.kind));
apply($('#association-form'),'associations',d=>({key:d.get('key'),source:d.get('source'),relationship:d.get('relationship'),target:d.get('target')}),newAssociation);
apply($('#occurrence-form'),'historical_occurrences',d=>({key:d.get('key'),participants:d.getAll('participants'),place:d.get('place'),world_time:Number(d.get('world_time')),system_time:Number(d.get('system_time')),synopsis:d.get('synopsis'),story:d.get('story'),started_associations:d.getAll('started_associations'),ended_associations:d.getAll('ended_associations')}),newOccurrence);
document.querySelectorAll('.tabs button').forEach(button=>button.onclick=()=>{document.querySelectorAll('.tabs button,.page').forEach(x=>x.classList.remove('active'));button.classList.add('active');$('#'+button.dataset.tab).classList.add('active')});
$('#identity-form').kind.addEventListener('change',()=>{const f=$('#identity-form');if(f.index.value==='')f.key.value=nextKey(f.kind.value==='ENTITY'?'e':f.kind.value==='PLACE'?'p':'d',world.identities)});
$('#save').onclick=async()=>{const status=$('#status');try{const response=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(world)});const result=await response.json();if(!response.ok)throw Error(result.error);status.textContent='Saved';status.className='saved'}catch(error){status.textContent='Cannot save: '+error.message;status.className='error'}};
Promise.all([fetch('/api/world').then(r=>r.json()),fetch('/api/meta').then(r=>r.json())]).then(([loaded,meta])=>{world=loaded;relationships=meta.relationships;$('#world-path').textContent='World: '+meta.world;render();newIdentity();newAssociation();newOccurrence()}).catch(error=>{$('#status').textContent=error.message;$('#status').className='error'});
</script></body></html>"""


def _json_bytes(value: object) -> bytes:
    return json.dumps(value).encode()


def _handler(
    *, package: Path, serializer: MemoryJsonSerializer
) -> type[BaseHTTPRequestHandler]:
    class WorldBuilderHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                self._respond(_PAGE.encode(), "text/html; charset=utf-8")
            elif self.path == "/api/world":
                world = serializer.load(package)
                self._respond(
                    _json_bytes(serializer.to_document(world)),
                    "application/json; charset=utf-8",
                )
            elif self.path == "/api/meta":
                relationships = [
                    item.name for item in RelationshipVocabulary.core().all()
                ]
                self._respond(
                    _json_bytes({"world": str(package), "relationships": relationships}),
                    "application/json; charset=utf-8",
                )
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in {"/api/save", "/api/validate"}:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 10_000_000:
                    raise ValueError("World document exceeds the 10 MB authoring limit.")
                raw = cast(object, json.loads(self.rfile.read(length)))
                world = serializer.from_document(raw)
                if self.path == "/api/save":
                    serializer.save(package, world)
                else:
                    validate_memory_document(serializer.to_document(world))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                self._respond(
                    _json_bytes({"error": str(exc)}),
                    "application/json; charset=utf-8",
                    HTTPStatus.BAD_REQUEST,
                )
                return
            result = {"saved": True} if self.path == "/api/save" else {"valid": True}
            self._respond(_json_bytes(result), "application/json; charset=utf-8")

        def _respond(
            self,
            body: bytes,
            content_type: str,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return WorldBuilderHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ChronoSpear World Builder.")
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8001, type=int)
    args = parser.parse_args()
    package = args.world.resolve()
    serializer = MemoryJsonSerializer()
    serializer.load(package)
    server = ThreadingHTTPServer(
        (args.host, args.port), _handler(package=package, serializer=serializer)
    )
    print(
        f"ChronoSpear World Builder: http://{args.host}:{server.server_port}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
