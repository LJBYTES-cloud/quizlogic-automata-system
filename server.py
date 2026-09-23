from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from automata import matches_any

BASE_DIR = Path(__file__).resolve().parent
QUIZ_FILE = BASE_DIR / "quiz.json"
DB_FILE = BASE_DIR / "quizlogic.db"
CSS_FILE = BASE_DIR / "static" / "style.css"


def load_quizzes():
    return json.loads(QUIZ_FILE.read_text(encoding="utf-8"))["quizzes"]


def get_quiz(quiz_id):
    return next((q for q in load_quizzes() if q["id"] == quiz_id), None)


def db_connect():
    db = sqlite3.connect(DB_FILE)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = db_connect()
    db.execute(
        """CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            percentage REAL NOT NULL,
            answers_json TEXT NOT NULL,
            matches_json TEXT NOT NULL,
            submitted_at TEXT NOT NULL
        )"""
    )
    db.commit()
    db.close()


def page(title, body):
    nav = """
    <header class='topbar'><div class='wrap nav'>
      <a class='brand' href='/'>QuizLogic</a>
      <nav><a href='/'>Quizzes</a><a href='/history'>History</a><a href='/admin'>Automata Rules</a></nav>
    </div></header>
    """
    return f"""<!doctype html>
<html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{escape(title)} · QuizLogic</title><link rel='stylesheet' href='/static/style.css'></head>
<body>{nav}<main class='wrap'>{body}</main><footer class='wrap footer'>Automata-Based Answer Recognition and Evaluation System</footer></body></html>"""


def home_html():
    cards = []
    for quiz in load_quizzes():
        cards.append(f"""<article class='card'><span class='tag'>{len(quiz['questions'])} questions</span>
        <h2>{escape(quiz['title'])}</h2><p>{escape(quiz['description'])}</p>
        <a class='button' href='/quiz/{escape(quiz['id'])}'>Start quiz</a></article>""")
    body = f"""<section class='hero'><p class='eyebrow'>FINITE AUTOMATA • REGULAR LANGUAGES • PATTERN MATCHING</p>
    <h1>QuizLogic</h1><p>Take a quiz and let a finite-state rule determine whether each answer belongs to the accepted language.</p></section>
    <div class='grid'>{''.join(cards)}</div>
    <div class='card info'><h2>How the system works</h2>
    <p><strong>Student answer → normalization → regular-expression rule → ε-NFA → DFA → accept/reject → score.</strong></p>
    <p>The backend constructs an automaton from each accepted pattern and tests the submitted answer against it.</p></div>"""
    return page("Quizzes", body)


def quiz_html(quiz):
    questions = []
    for i, q in enumerate(quiz["questions"], 1):
        if q["type"] == "mcq":
            options = ''.join(
                f"<label class='option'><input type='radio' name='q_{q['id']}' value='{escape(o)}' required><span>{escape(o)}</span></label>"
                for o in q["options"]
            )
            input_html = f"<div class='options'>{options}</div>"
        else:
            input_html = f"<input name='q_{q['id']}' type='text' placeholder='Type your answer' autocomplete='off' required>"
        questions.append(f"""<article class='question card'><div class='question-number'>Question {i} · {q['points']} pt</div>
        <h2>{escape(q['question'])}</h2>{input_html}</article>""")
    body = f"""<section class='hero compact'><p class='eyebrow'>QUIZ</p><h1>{escape(quiz['title'])}</h1>
    <p>{escape(quiz['description'])}</p></section>
    <form class='quiz-form' method='post' action='/submit/{escape(quiz['id'])}'>
      <div class='card student-card'><label for='student_name'>Student name</label>
      <input id='student_name' name='student_name' type='text' placeholder='Enter your name' required></div>
      {''.join(questions)}
      <button class='button primary' type='submit'>Submit quiz</button>
    </form>"""
    return page(quiz["title"], body)


def result_html(quiz, student_name, score, total, percentage, feedback, attempt_id):
    items = []
    for i, item in enumerate(feedback, 1):
        status = "Accepted by automaton" if item["correct"] else "Rejected by automaton"
        matched = f"<p class='muted'>Matched rule: <code>{escape(item['matched_pattern'])}</code></p>" if item["matched_pattern"] else ""
        items.append(f"""<article class='feedback card {'correct' if item['correct'] else 'incorrect'}'>
        <div class='feedback-head'><h2>Question {i}</h2><span>{item['earned']}/{item['points']}</span></div>
        <p>{escape(item['question'])}</p><p><strong>Your answer:</strong> {escape(item['answer']) or 'No answer'}</p>
        <p class='status'>{status}</p>{matched}<p class='muted'>{escape(item['explanation'])}</p></article>""")
    body = f"""<section class='result card'><p class='eyebrow'>RESULT</p><h1>{escape(student_name)}</h1>
    <div class='score'>{score} / {total}</div><p class='percentage'>{percentage}%</p><p>Attempt #{attempt_id} · {escape(quiz['title'])}</p></section>
    {''.join(items)}
    <div class='actions'><a class='button' href='/quiz/{escape(quiz['id'])}'>Retake quiz</a><a class='button secondary' href='/history'>View history</a></div>"""
    return page("Quiz Result", body)


def history_html():
    db = db_connect()
    rows = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 50").fetchall()
    db.close()
    body_rows = []
    for a in rows:
        submitted = a["submitted_at"][:19].replace("T", " ")
        body_rows.append(f"<tr><td>#{a['id']}</td><td>{escape(a['student_name'])}</td><td>{escape(a['quiz_id'])}</td><td>{a['score']}/{a['total']}</td><td>{a['percentage']}%</td><td>{submitted} UTC</td></tr>")
    if not body_rows:
        body_rows.append("<tr><td colspan='6'>No attempts yet.</td></tr>")
    body = f"""<section class='hero compact'><p class='eyebrow'>RECORDS</p><h1>Attempt History</h1>
    <p>The local SQLite database stores recent quiz submissions.</p></section>
    <div class='card table-card'><table><thead><tr><th>Attempt</th><th>Student</th><th>Quiz</th><th>Score</th><th>Percent</th><th>Submitted</th></tr></thead>
    <tbody>{''.join(body_rows)}</tbody></table></div>"""
    return page("Attempt History", body)


def admin_html():
    blocks = []
    for quiz in load_quizzes():
        rules = []
        for q in quiz["questions"]:
            rules.append(f"<div class='rule'><div><strong>Q{q['id']}.</strong> {escape(q['question'])}</div><code>{escape(' | '.join(q['patterns']))}</code></div>")
        blocks.append(f"<div class='card rule-card'><h2>{escape(quiz['title'])}</h2>{''.join(rules)}</div>")
    body = f"""<section class='hero compact'><p class='eyebrow'>TEACHER / DEVELOPER VIEW</p><h1>Automata Rules</h1>
    <p>These regular-language patterns are compiled into NFAs and then DFAs for answer validation.</p></section>
    {''.join(blocks)}
    <div class='card info'><h2>Supported pattern syntax</h2>
    <p><code>|</code> OR · <code>()</code> grouping · <code>*</code> zero or more · <code>+</code> one or more · <code>?</code> optional · <code>.</code> any character · <code>[ab]</code> class · <code>[a-z]</code> range.</p></div>"""
    return page("Automata Rules", body)


class QuizHandler(BaseHTTPRequestHandler):
    def send_html(self, body, status=200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_text(self, body, content_type="text/plain; charset=utf-8", status=200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self.send_html(home_html())
        if path.startswith("/quiz/"):
            quiz = get_quiz(path.split("/", 2)[2])
            if not quiz:
                return self.send_html(page("Not Found", "<div class='card'><h1>Quiz not found</h1></div>"), 404)
            return self.send_html(quiz_html(quiz))
        if path == "/history":
            return self.send_html(history_html())
        if path == "/admin":
            return self.send_html(admin_html())
        if path == "/static/style.css":
            return self.send_text(CSS_FILE.read_text(encoding="utf-8"), "text/css; charset=utf-8")
        return self.send_html(page("Not Found", "<div class='card'><h1>404</h1></div>"), 404)

    def do_POST(self):
        try:
            path = urlparse(self.path).path
            if not path.startswith("/submit/"):
                return self.send_html(page("Not Found", "<div class='card'><h1>404</h1></div>"), 404)
            quiz = get_quiz(path.split("/", 2)[2])
            if not quiz:
                return self.send_html(page("Not Found", "<div class='card'><h1>Quiz not found</h1></div>"), 404)
        
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            form = parse_qs(raw, keep_blank_values=True)
            student_name = form.get("student_name", ["Student"])[0].strip() or "Student"
            score = 0
            total = sum(q.get("points", 1) for q in quiz["questions"])
            answers, matched_rules, feedback = {}, {}, []
        
            for q in quiz["questions"]:
                answer = form.get(f"q_{q['id']}", [""])[0]
                matched = matches_any(answer, q["patterns"])
                correct = matched is not None
                points = q.get("points", 1)
                earned = points if correct else 0
                score += earned
                answers[str(q["id"])] = answer
                matched_rules[str(q["id"])] = matched
                feedback.append({
                    "question": q["question"], "answer": answer, "correct": correct,
                    "earned": earned, "points": points, "matched_pattern": matched,
                    "explanation": q.get("explanation", "")
                })
        
            percentage = round(score / total * 100, 2) if total else 0
            db = db_connect()
            cur = db.execute(
                "INSERT INTO attempts (quiz_id, student_name, score, total, percentage, answers_json, matches_json, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (quiz["id"], student_name, score, total, percentage, json.dumps(answers), json.dumps(matched_rules), datetime.now(timezone.utc).isoformat())
            )
            db.commit()
            attempt_id = cur.lastrowid
            db.close()
            return self.send_html(result_html(quiz, student_name, score, total, percentage, feedback, attempt_id))
        
        except Exception as exc:
            import traceback
            traceback.print_exc()
            try:
                self.send_html(page("Server Error", "<div class=\'card\'><h1>500</h1><p>" + escape(str(exc)) + "</p></div>"), 500)
            except Exception:
                pass

    def log_message(self, _format, *args):
        return


if __name__ == "__main__":
    init_db()
    server = ThreadingHTTPServer(("127.0.0.1", 5000), QuizHandler)
    print("QuizLogic running at http://127.0.0.1:5000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
