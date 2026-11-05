# Project rules (generic version)

A first-person horror game demo in Godot (20-25 minutes). One human directs several Claude Code sessions.
Journal: `JOURNAL.md`. Who does what: `docs/sessions.md` (read your section; the session-start script says "YOU ARE: ...").

## Talking to her
- Plain words, one decision at a time, no assumed technical background.
- She only talks to the human-facing sessions; between sessions, everything goes through the mailbox (`docs/sessions.md`).

## What protects (no exception)
- **The reference register is the source of truth**: nothing is modelled, textured or given a sound without an
  **approved** line in `refs/REFS.md` (grey prototype blocks do not need one). A web reference is approved only on her
  yes; only she adds to the approved folder (a human-only script, never run by Claude).
- `refs/approved/` and `docs/story_bible/`: **read-only**. The story's source of truth is the story bible; notes about it are only notes.
- **No generative model** for assets (image, video, texture, 3D, sound), no NC or ND licence. Allowed: code that
  computes, human-made CC0/CC-BY assets.
- **Safety**: never bypass mode; Blender only through MCP, never `blender -b`; never work around the guard; a new MCP
  server is checked before use; an installer: official site, signature, antivirus scan, then tell her.
- **Nothing that costs** (money, quota, credits) without her yes.
- **Tests**: never weakened or removed without her yes. Commits only through `/end`, never a `git add` that names a protected folder.

## Making the game
1. **The experience goal first** (Tracy Fullerton, *Game Design Workshop*): before any mechanic, one sentence in her
   words of what she wants to feel while playing; every prototype is judged against it first. One game rule, serving it.
2. **A mechanic is played before it is judged**: a 1-2 h grey prototype, played by her for 10 min without explanation,
   3 criteria fixed beforehand; 2 missed -> the rule is thrown away, not patched: the criteria decide, not the wish.
3. **Before any new direction, in order**: the sentence (1), research on how professionals did it (a sub-agent; games,
   artists, and open-source projects with over 1000 stars, checked before integrating), 2-3 proposals, the pre-mortem and
   the fixed time (9), then the prototype (2).
4. **Grey blocks first**, final art after. Blender builds the geometry (MCP), Godot assembles and judges; a piece made
   twice becomes a function of the kit.
5. **The playtest bot comes last**.
6. A reviewer agent only judges what can be seen or heard. **The target image**: one image drawn from her references,
   approved once by her; every game capture is put next to it before being shown.
7. **The code is the source of truth**: a doc that contradicts it is fixed, and the gap is said out loud (never the
   approved references or the story bible).
8. Read the useful files first, in one go; then edit; then test once; at the end of the task, one line on what was not tested.
9. **The pre-mortem** (Gary Klein, 2007): before any new direction, I write in three lines why it will have failed in two
   days, my recommendation (including "don't do it") and the sign that will make us stop. If I disagree with her, I say
   it once with my reasons; she decides, and I stick to it. **The fixed time** (Ryan Singer, *Shape Up*): every piece of
   work has a time chosen with her before starting, started on the timer (`python -I hooks/timer.py --start <role> <min> "<work>"`;
   once it is up, the guard blocks what changes the game, except at night where only the quota stops). When the time is
   up, we stop without extending, and I ask her again instead of making a new version.

## Tools
- Test Godot: `--audio-driver Dummy`, off-screen, closed afterwards.
- Sub-agents at medium effort; long reads (research, journals, big files) go through them, to keep the conversation in the smart zone.
- Skills: `/start` `/end` every session, `/improve`, and the project's own.

## Against dust
- Caps: this file 40 lines; 8 memories, 80 words each; a production task in 3 lines. A script counts them at every `/start` and `/end`.
- One rule in, one rule out: a rule is added only on her yes, saying which one is merged or removed. A rule lives in one place only.
- A rule tied to a moment carries its end date `(until YYYY-MM-DD)`.
- **Review every Monday**, at `/start`: the list of rules, she removes what she wants.
