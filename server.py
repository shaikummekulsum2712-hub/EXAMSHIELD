"""
ExamShield KMP server (standard library only, plus the bundled `segno` for the QR code).
Run:  python3 server.py [port]      then open http://localhost:8000/proctor on the teacher laptop.
"""
import io, json, os, socket, sys, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "vendor"))
from kmp import SIGNATURES, StreamKMP, StreamBrute, build_lps

LOCK = threading.Lock()
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

SAMPLE_QUIZ = [
    {"q": "What is the time complexity of building the KMP LPS table for a pattern of length m?",
     "options": ["O(m)", "O(m^2)", "O(n*m)", "O(log m)"], "answer": 0,
     "variant": "How much time does it take to construct the KMP failure function for a pattern with m characters?"},
    {"q": "In KMP, what does LPS[i] store?",
     "options": ["Longest proper prefix of pattern[0..i] that is also its suffix", "Position of the last mismatch",
                 "Number of matches so far", "Length of the text"], "answer": 0,
     "variant": "For index i of the KMP failure table, which value is kept?"},
    {"q": "Which data structure gives O(1) average lookup in a hash table?",
     "options": ["Array of buckets", "Linked list only", "Binary heap", "Stack"], "answer": 0,
     "variant": "A hash table reaches O(1) average access mainly because of which underlying structure?"},
    {"q": "Worst-case time of brute-force string matching (text n, pattern m)?",
     "options": ["O(n*m)", "O(n+m)", "O(n log m)", "O(m)"], "answer": 0,
     "variant": "How many steps can naive pattern search take at most when the text has n and the pattern m characters?"},
    {"q": "Which algorithm never moves the text pointer backwards?",
     "options": ["KMP", "Brute force", "Bubble sort", "Binary search"], "answer": 0,
     "variant": "Pick the string-matching method whose text index only ever moves forward."},
]

EXAM = {"title": "Sample CS Quiz", "questions": SAMPLE_QUIZ, "published": False}
STUDENTS = {}   # name -> dict
TOTALS = {"kmp_cmp": 0, "brute_cmp": 0, "events": 0}
HOST_IP = "127.0.0.1"


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def gemini_variant(question):
    """Asks Gemini for a reworded question. Needs GEMINI_API_KEY + internet. Returns None on any failure."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    try:
        prompt = ("Reword this exam question so it tests the same concept but has different wording. "
                  "Keep the same options. Reply with ONLY the new question text.\n\n" + question["q"])
        body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
        url = ("https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=" + key)
        req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
        data = json.loads(urllib.request.urlopen(req, timeout=6).read())
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print("Gemini failed, using fallback:", e)
        return None


def new_student(name):
    return {"name": name, "stream": "", "q": 0, "joined": time.time(), "flags": [], "pending_variant": None,
            "kmp": {p: StreamKMP(p) for p in SIGNATURES},
            "brute": {p: StreamBrute(p) for p in SIGNATURES}, "answers": {}}


def process_token(st, token, qno):
    """Feeds ONE event into every pattern matcher of this student. This is the streaming KMP step."""
    st["stream"] += token
    st["q"] = qno
    TOTALS["events"] += 1
    fired = []
    for p in SIGNATURES:
        before_k, before_b = st["kmp"][p].comparisons, st["brute"][p].comparisons
        hit = st["kmp"][p].feed(token)
        st["brute"][p].feed(token)
        TOTALS["kmp_cmp"] += st["kmp"][p].comparisons - before_k
        TOTALS["brute_cmp"] += st["brute"][p].comparisons - before_b
        if hit:
            fired.append(p)
    # when several fire on the same event, report the longest (most specific) one
    if fired:
        p = max(fired, key=len)
        flag = {"pattern": p, "meaning": SIGNATURES[p], "question": qno + 1, "time": time.strftime("%H:%M:%S"),
                "lps": build_lps(p), "stream_tail": st["stream"][-12:]}
        st["flags"].append(flag)
        q = EXAM["questions"][qno] if 0 <= qno < len(EXAM["questions"]) else None
        if q:
            threading.Thread(target=make_variant, args=(st, qno, q), daemon=True).start()


def make_variant(st, qno, q):
    text = gemini_variant(q)
    source = "gemini"
    if not text:
        text, source = q.get("variant") or q["q"], "prepared"
    with LOCK:
        st["pending_variant"] = {"q": qno, "text": text, "source": source}


def public_exam():
    return {"title": EXAM["title"], "published": EXAM["published"],
            "questions": [{"q": x["q"], "options": x["options"]} for x in EXAM["questions"]]}


def state_json():
    rows = []
    for st in STUDENTS.values():
        rows.append({"name": st["name"], "events": len(st["stream"]), "stream": st["stream"][-40:], "q": st["q"] + 1,
                     "flags": st["flags"],
                     "kmp_state": {p: st["kmp"][p].state for p in SIGNATURES},
                     "kmp_cmp": sum(m.comparisons for m in st["kmp"].values()),
                     "brute_cmp": sum(m.comparisons for m in st["brute"].values()),
                     "answered": len(st["answers"])})
    return {"exam": {"title": EXAM["title"], "published": EXAM["published"], "n": len(EXAM["questions"])},
            "patterns": {p: {"meaning": m, "lps": build_lps(p)} for p, m in SIGNATURES.items()},
            "totals": TOTALS, "students": rows}


def qr_svg(url):
    import segno
    b = io.BytesIO()
    segno.make(url, error="m").save(b, kind="svg", scale=8, border=2, dark="#111", light="#fff")
    return b.getvalue()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, body, ctype="application/json", code=200):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8" if "text" in ctype or "json" in ctype else ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def page(self, name):
        with open(os.path.join(HERE, "web", name), "rb") as f:
            self.send(f.read(), "text/html")

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if u.path in ("/", "/proctor"):
            return self.page("proctor.html")
        if u.path == "/student":
            return self.page("student.html")
        if u.path == "/qr.svg":
            return self.send(qr_svg("http://%s:%d/student" % (HOST_IP, PORT)), "image/svg+xml")
        if u.path == "/api/info":
            return self.send({"url": "http://%s:%d/student" % (HOST_IP, PORT)})
        with LOCK:
            if u.path == "/api/exam":
                return self.send(public_exam())
            if u.path == "/api/state":
                return self.send(state_json())
            if u.path == "/api/poll":
                st = STUDENTS.get(qs.get("name", [""])[0])
                v = None
                if st and st["pending_variant"]:
                    v, st["pending_variant"] = st["pending_variant"], None
                return self.send({"variant": v, "published": EXAM["published"]})
        self.send({"error": "not found"}, code=404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self.send({"error": "bad json"}, code=400)
        path = urlparse(self.path).path
        with LOCK:
            if path == "/api/publish":
                if data.get("questions"):
                    qs_ = []
                    for x in data["questions"]:
                        qs_.append({"q": str(x["q"])[:300], "options": [str(o)[:120] for o in x["options"]][:4],
                                    "answer": int(x.get("answer", 0)), "variant": x.get("variant")})
                    EXAM["questions"] = qs_
                    EXAM["title"] = str(data.get("title", "Quiz"))[:80]
                else:
                    EXAM["questions"], EXAM["title"] = SAMPLE_QUIZ, "Sample CS Quiz"
                EXAM["published"] = True
                STUDENTS.clear()
                TOTALS.update(kmp_cmp=0, brute_cmp=0, events=0)
                return self.send({"ok": True})
            if path == "/api/reset":
                EXAM["published"] = False
                STUDENTS.clear()
                TOTALS.update(kmp_cmp=0, brute_cmp=0, events=0)
                return self.send({"ok": True})
            if path == "/api/join":
                name = str(data.get("name", "")).strip()[:20]
                if not name:
                    return self.send({"error": "name needed"}, code=400)
                STUDENTS.setdefault(name, new_student(name))
                return self.send({"ok": True, "name": name})
            if path == "/api/log":
                st = STUDENTS.get(data.get("name"))
                tok = str(data.get("token", ""))[:1]
                if not st or tok not in "CBIPAN" or not tok:
                    return self.send({"error": "bad"}, code=400)
                process_token(st, tok, int(data.get("q", 0)))
                return self.send({"ok": True})
            if path == "/api/answer":
                st = STUDENTS.get(data.get("name"))
                if st:
                    st["answers"][int(data.get("q", 0))] = int(data.get("choice", -1))
                return self.send({"ok": True})
        self.send({"error": "not found"}, code=404)


if __name__ == "__main__":
    HOST_IP = lan_ip()
    print("ExamShield KMP running.")
    print("  Teacher dashboard : http://localhost:%d/proctor" % PORT)
    print("  Students (same Wi-Fi): http://%s:%d/student  (QR is on the dashboard)" % (HOST_IP, PORT))
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
