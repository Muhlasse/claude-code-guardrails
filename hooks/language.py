# Stop hook: re-reads the texts Claude wrote for the human since her last message and, if they are in English
# while she works in French, blocks the end of the turn and asks for everything again in French.
# Added after several progress messages arrived in English: a written rule was not enough, a hook was.
# Simple measure: count the most common short English and French words; code in ` ` and ``` blocks and links are ignored.
# Only one nudge per turn (stop_hook_active), so it can never loop.
import json, re, sys

EN = set("the and you your is are was were this that it's i'm i'll i've we we're they there here with for from what which have has "
         "not but can will would should could don't doesn't now then just also into about before after because so if it of to on "
         "in at by be been being do does did".split())
FR = set("le la les et tu ton ta tes est sont était ce cette c'est je j'ai nous il elle on pour avec dans que qui quoi pas "
         "mais peux vais va fait faire aussi puis donc car si de du des un une sur en au aux par être été ça".split())


def texts_since_her(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    out = []
    for l in reversed(lines):
        try:
            d = json.loads(l)
        except Exception:
            continue
        m = d.get("message") or {}
        c = m.get("content")
        if d.get("type") == "user":
            # her real message (text), not a tool result: stop there
            if isinstance(c, str) or (isinstance(c, list) and any(b.get("type") == "text" for b in c if isinstance(b, dict))):
                if not (isinstance(c, list) and any(b.get("type") == "tool_result" for b in c if isinstance(b, dict))):
                    break
        if d.get("type") == "assistant" and isinstance(c, list):
            out += [b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"]
    return out


def is_english(t):
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"`[^`]*`", " ", t)
    t = re.sub(r"https?://\S+", " ", t)
    words = re.findall(r"[a-zA-Z']+", t.lower())
    en = sum(w in EN for w in words)
    fr = sum(w in FR for w in words)
    return en >= 4 and en > fr


if __name__ == "__main__":
    try:
        d = json.loads(sys.stdin.buffer.read().decode('utf-8', 'replace'))   # UTF-8, not cp1252
        if d.get("stop_hook_active"):          # already nudged once: no loop
            sys.exit(0)
        wrong = [t for t in texts_since_her(d["transcript_path"]) if is_english(t)]
        if wrong:
            print(json.dumps({"decision": "block", "reason":
                "Some messages for her are in ENGLISH (" + wrong[0][:80].replace("\n", " ") + "...). "
                "She has seen them: apologise in one line and give their useful content again IN FRENCH. "
                "From now on, write everything, even progress messages, in French."}))
    except Exception:
        pass
    sys.exit(0)
