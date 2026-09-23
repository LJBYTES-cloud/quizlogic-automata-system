# QuizLogic

## Automata-Based Answer Recognition and Evaluation System

This is a small, practical web system built around the requirements in the project brief:

- Finite State Machines
- Regular Languages
- Pattern Matching
- Answer Validation
- Automatic Checking
- Pattern-Based Evaluation
- Score Generation

### Core flow

**Student answer → normalization → regular-expression rule → epsilon-NFA → DFA → accept/reject → score → SQLite record**

The important part for an Automata Theory project is that the validator does not simply use Python's built-in regex engine. `automata.py` implements a small regular-expression parser, constructs a Thompson epsilon-NFA, converts it to a DFA with subset construction, and then uses the DFA to recognize the submitted answer.

### Run

Requires Python 3.9+ and no third-party packages.

```bash
python server.py
```

Then open:

`http://127.0.0.1:5000`

Stop the server with `Ctrl+C`.

### System pages

`/` — quiz list

`/quiz/automata-basics` — student quiz page

`/admin` — teacher/developer view of answer patterns

`/history` — stored attempts and scores

### Editing questions

Edit `quiz.json`. Each question contains:

- `type`: `mcq` or `short`
- `options`: used for MCQ questions
- `patterns`: accepted regular-language patterns
- `points`: score value
- `explanation`: shown after submission

Example:

```json
"patterns": ["fsm", "finite state machine", "finite state machines"]
```

Multiple patterns mean that several answers can be accepted.

Example:

```json
"patterns": ["[ab]+"]
```

accepts one or more `a` or `b` characters.

### Pattern syntax

| Syntax | Meaning |
|---|---|
| `A|B` | A or B |
| `(ab)` | grouping |
| `a*` | zero or more |
| `a+` | one or more |
| `a?` | optional |
| `.` | any character |
| `[ab]` | character class |
| `[a-z]` | character range |

Patterns are matched as complete answers. Student input is case-folded, whitespace-normalized, and punctuation-normalized before it enters the automaton.

### Database

The first run creates `quizlogic.db` automatically using SQLite. Each attempt stores the quiz ID, student name, score, percentage, submitted answers, matched rules, and timestamp.

### File structure

```text
quizlogic/
├── server.py
├── automata.py
├── quiz.json
├── README.md
├── .gitignore
└── static/
    └── style.css
```

### Demonstration for class

A clean demo is:

1. Answer some questions correctly and some incorrectly.
2. Submit the quiz and show the score.
3. Point out `Accepted by automaton` and `Rejected by automaton`.
4. Open **Automata Rules** and show the accepted patterns.
5. Open **History** and show saved attempts.
6. In `automata.py`, explain `RegexParser`, `nfa_to_dfa`, and `DFA.accepts_text` as the implementation of the automata concepts.

This is intentionally scoped as a local academic prototype rather than a production online examination platform. It has no login system or public deployment layer.
