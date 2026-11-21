# ExamShield KMP
Detects phone-based cheating in a live quiz by running streaming KMP on each student's behaviour stream.

## Run
    python3 server.py            # port 8000 (or: python3 server.py 9000)
Teacher laptop: http://localhost:8000/proctor  -> press "Use sample CS quiz" (or type your own questions).
Students: scan the QR on the dashboard (same Wi-Fi / phone hotspot as the laptop).
No phones handy? Use the "Demo without phones" buttons on the dashboard.
Optional Gemini rewording:  GEMINI_API_KEY=your_key python3 server.py   (without it, a prepared reworded question is used)

## Test
    python3 -I tests/test_kmp.py                     # unit tests
    PYTHONPATH=. python3 benchmark.py                # big-stream experiments -> results/benchmark.json
    python3 make_graphs.py
    (server running on 8123)  PYTHONPATH=. python3 tests/e2e.py   # needs: pip install playwright

## Files
kmp.py (algorithm) · server.py · web/student.html · web/proctor.html · tests/ · benchmark.py · vendor/ (QR library segno, bundled)
