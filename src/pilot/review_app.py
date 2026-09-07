"""Local blinded review interface for the association pilot.

Deliberate properties:

  * Local only. Binds to 127.0.0.1; there is no remote mode.
  * Serves nothing but the three orthogonal views of one item plus three buttons. No
    caption, no explanation, no suggested answer, no model output. There is no code path
    that could prefill or alter a label -- the server accepts a label from an HTTP POST and
    hands it to `ReviewStore`, which rejects anything that is not one of the three permitted
    values from a registered human reviewer.
  * Blinded. Items are addressed by opaque `review_item_id`. Patient/series/session
    identity, category, distance, threshold, and repeat-subset membership are never sent to
    the browser, and rendered images are named by opaque id only.
  * Resumable. Progress is derived from the append-only store, so an interrupted session
    continues where it stopped.
  * Repeat-round items are indistinguishable from primary items in the interface.

Rendering is intentionally separated from serving: `render_item()` takes a volume-provider
callable so the synthetic smoke test can exercise the whole interface with no patient data.
"""

from __future__ import annotations

import io
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from .review_store import LABELS, REASON_CODES, LabelRejected, ReviewStore

APP_VERSION = "review-app-v1"

#: Fixed window/level for every item. Identical visualisation rules for all items, so
#: appearance never varies in a way that could bias a judgement.
WINDOW_HU = (-1000.0, 400.0)
CONTEXT_SLICES = 2          # adjacent slices each side, for 3D continuity
OVERLAY_A = "#00d0ff"       # mark A -- neutral, distinguishable
OVERLAY_B = "#ffb000"       # mark B


def window_to_unit(array, lo: float = WINDOW_HU[0], hi: float = WINDOW_HU[1]):
    import numpy as np
    return np.clip((np.asarray(array, dtype="float32") - lo) / (hi - lo), 0.0, 1.0)


def render_item(
    review_item_id: str,
    volume_provider: Callable[[str], dict],
    out_dir: str,
) -> list[str]:
    """Render synchronized axial/coronal/sagittal PNGs for one review item.

    `volume_provider(review_item_id)` returns a dict with keys:
        volume        3-D array in HU, indexed [row, col, slice]
        spacing_mm    (row, col, slice) spacing, for consistent physical scale
        mark_a        (row, col, slice) voxel centre of mark A
        mark_b        (row, col, slice) voxel centre of mark B
    The provider is the ONLY component that touches image data, so the interface can be
    tested end-to-end against synthetic volumes.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    data = volume_provider(review_item_id)
    vol = window_to_unit(data["volume"])
    sr, sc, ss = data["spacing_mm"]
    a, b = data["mark_a"], data["mark_b"]
    mid = tuple(int(round((a[i] + b[i]) / 2)) for i in range(3))

    os.makedirs(out_dir, exist_ok=True)
    written: list[str] = []
    planes = (
        ("axial", lambda k: vol[:, :, k], 2, (sc, sr), (1, 0)),
        ("coronal", lambda k: vol[k, :, :], 0, (ss, sc), (2, 1)),
        ("sagittal", lambda k: vol[:, k, :], 1, (ss, sr), (2, 0)),
    )
    for name, slicer, axis, (asp_x, asp_y), (px, py) in planes:
        n = vol.shape[axis]
        centre = min(max(mid[axis], 0), n - 1)
        idxs = [i for i in range(centre - CONTEXT_SLICES, centre + CONTEXT_SLICES + 1)
                if 0 <= i < n]
        fig, axes = plt.subplots(1, len(idxs), figsize=(2.1 * len(idxs), 2.4))
        if len(idxs) == 1:
            axes = [axes]
        for ax, k in zip(axes, idxs):
            ax.imshow(slicer(k), cmap="gray", vmin=0.0, vmax=1.0,
                      aspect=(asp_x / asp_y) if asp_y else 1.0)
            for mark, colour in ((a, OVERLAY_A), (b, OVERLAY_B)):
                if abs(int(round(mark[axis])) - k) <= CONTEXT_SLICES:
                    ax.plot(mark[px], mark[py], marker="o", markersize=11,
                            markerfacecolor="none", markeredgecolor=colour,
                            markeredgewidth=1.8)
            ax.set_axis_off()
        fig.suptitle(name, fontsize=9)          # plane name only; never a judgement
        fig.tight_layout()
        path = os.path.join(out_dir, f"{review_item_id}__{name}.png")
        fig.savefig(path, dpi=90)
        plt.close(fig)
        written.append(path)
    return written


_PAGE = """<!doctype html><meta charset=utf-8><title>Pair review</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;background:#111;color:#eee}
 header{padding:.6rem 1rem;background:#1b1b1b;display:flex;gap:1.5rem;align-items:center}
 .views img{max-width:100%;display:block;margin:.4rem auto;background:#000}
 .bar{display:flex;gap:.75rem;padding:1rem;justify-content:center;flex-wrap:wrap}
 button{font-size:1rem;padding:.7rem 1.1rem;border:1px solid #444;border-radius:6px;
   background:#222;color:#eee;cursor:pointer}
 button:hover{background:#2c2c2c}
 .key{display:flex;gap:1rem;font-size:.85rem;padding:0 1rem}
 .sw{display:inline-block;width:.8rem;height:.8rem;border-radius:50%;border:2px solid}
</style>
<header>
  <strong>Do the two circled marks refer to the same physical lesion?</strong>
  <span id=prog></span>
</header>
<div class=key>
  <span><span class=sw style="border-color:#00d0ff"></span> mark A</span>
  <span><span class=sw style="border-color:#ffb000"></span> mark B</span>
  <span>window/level fixed &middot; consistent physical scale</span>
</div>
<div class=views id=views></div>
<div class=bar>
  <button onclick="send('same_physical_lesion')">Same physical lesion</button>
  <button onclick="send('different_physical_lesion')">Different physical lesions</button>
  <button onclick="send('indeterminate')">Indeterminate</button>
</div>
<script>
let item=null;
async function load(){
  const r=await fetch('/api/next');const d=await r.json();
  if(d.done){document.getElementById('views').innerHTML=
     '<pre style="padding:2rem">'+d.summary+'</pre>';
   document.querySelector('.bar').style.display='none';
   document.getElementById('prog').textContent='complete';return;}
  item=d.review_item_id;
  document.getElementById('prog').textContent=d.completed+' / '+d.total+' reviewed';
  document.getElementById('views').innerHTML=
    d.images.map(s=>'<img src="'+s+'">').join('');
}
async function send(label){
  if(!item)return;
  await fetch('/api/label',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({review_item_id:item,label:label})});
  item=null;load();
}
load();
</script>
"""


class ReviewServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, handler, *, store: ReviewStore, items: list[str],
                 reviewer_id: str, round_name: str, image_dir: str):
        super().__init__(addr, handler)
        self.store = store
        self.items = items                 # already in display order
        self.reviewer_id = reviewer_id
        self.round_name = round_name
        self.image_dir = image_dir


class ReviewHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):          # keep the console clean for the reviewer
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        srv: ReviewServer = self.server              # type: ignore[assignment]
        if self.path in ("/", "/index.html"):
            self._send(200, _PAGE.encode(), "text/html; charset=utf-8")
            return
        if self.path == "/api/next":
            done = srv.store.completed_items(srv.round_name, srv.reviewer_id)
            remaining = [i for i in srv.items if i not in done]
            if not remaining:
                prog = srv.store.progress(srv.round_name, srv.reviewer_id, len(srv.items))
                # Completion summary only. Nothing about threshold performance.
                summary = json.dumps({k: prog[k] for k in
                                      ("round", "completed", "total", "label_counts",
                                       "indeterminate_fraction")}, indent=2)
                self._send(200, json.dumps({"done": True, "summary": summary}).encode(),
                           "application/json")
                return
            item = remaining[0]
            imgs = [f"/img/{os.path.basename(p)}" for p in sorted(
                f for f in os.listdir(srv.image_dir) if f.startswith(item + "__"))]
            payload = {"done": False, "review_item_id": item, "images": imgs,
                       "completed": len(done), "total": len(srv.items)}
            self._send(200, json.dumps(payload).encode(), "application/json")
            return
        if self.path.startswith("/img/"):
            name = os.path.basename(self.path[len("/img/"):])
            path = os.path.join(srv.image_dir, name)
            if not os.path.isfile(path):
                self._send(404, b"not found", "text/plain")
                return
            with open(path, "rb") as fh:
                self._send(200, fh.read(), "image/png")
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        srv: ReviewServer = self.server              # type: ignore[assignment]
        if self.path != "/api/label":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        try:
            record = srv.store.save_label(
                review_item_id=str(body.get("review_item_id", "")),
                reviewer_id=srv.reviewer_id,
                label=str(body.get("label", "")),
                round_name=srv.round_name,
                reason_code=str(body.get("reason_code", "no_reason_given")),
            )
        except LabelRejected as exc:
            self._send(400, json.dumps({"error": str(exc)}).encode(), "application/json")
            return
        self._send(200, json.dumps({"ok": True, "record_id": record["record_id"]}).encode(),
                   "application/json")


def serve(*, store: ReviewStore, items: list[str], reviewer_id: str, round_name: str,
          image_dir: str, port: int = 8765) -> ReviewServer:
    """Start the local server. Caller is responsible for shutdown."""
    return ReviewServer(("127.0.0.1", port), ReviewHandler, store=store, items=items,
                        reviewer_id=reviewer_id, round_name=round_name,
                        image_dir=image_dir)


__all__ = ["render_item", "serve", "ReviewServer", "ReviewHandler", "LABELS", "REASON_CODES",
           "WINDOW_HU", "APP_VERSION"]
