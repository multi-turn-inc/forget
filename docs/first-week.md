# Your first week with forget

forget gives your AI tools one persistent memory on your machine. This page
sets honest expectations: what happens on day one, what to check when it
feels like nothing is happening, and when the payoff arrives.

## Day 0 — install ends with a checkup

```
curl -fsSL forget.sh | sh
```

The installer finishes by running `forget-server doctor`. Green means the
whole nervous system works: server up, memory endpoint answering, store
sound, your pool clean. If any line is red, it comes with its fix — and if
you're stuck, send that exact output to whoever invited you.

## Days 1–2 — quiet, by design

A broken install and a healthy day-one install *feel identical*: nothing
visible happens. That's why doctor exists — it's the only honest way to
tell them apart. If doctor is green, memory is accumulating with every
session, silently. There is simply nothing worth recalling yet.

What's happening under the hood: decisions, preferences, and open tasks
from your sessions are being distilled and stored — on your machine, in
`~/.forget`, and nowhere else.

## The moment it clicks — the reboot ritual

Don't wait for it to happen naturally. Force it, once, on day two or three:

1. Start a real task in your AI tool (claude, codex — anything).
2. Kill the session mid-task. Really quit it.
3. Reopen and just say "continue".

A stateless agent greets you like a brilliant stranger. This one starts
with a handover: your goal, the next step, what changed. That's the product.

## "Does it eat my tokens?"

It trades, rather than eats: ~320 tokens once at session start, up to ~200
on turns where a relevant memory exists, zero on the write side (that runs
in the server process, outside your conversation). What that replaces:
re-explaining yourself (hundreds to thousands of tokens a time), or
stuffing history into context — in our benchmark the stuffing approach
spent 115k tokens for 60.6% accuracy; forget spent ~2k for 78.4%.

## When something feels off

```
~/.forget/venv/bin/forget-server doctor    # server side
npx forget-connect doctor                  # client wiring
```

Every red line ships with its prescription. Nothing about your memories
ever leaves your machine — including when you report a problem: you see
exactly what you send.
