You proposed a puzzle level and the verifier (validator + exhaustive solver + real engine) rejected
it. Fix the level. The findings are facts about your layout, not suggestions.

Return ONLY JSON: {"change": "<one sentence: what you changed and why>", "dsl": "<corrected level>"}

Same format rules as before: one row per line (use \n), single spaces, equal row lengths,
UPPERCASE = text tile, lowercase = object, "." = empty, 6 rows, generation vocabulary only.
Typical causes: a sentence that is not actually adjacent in reading order; a word against an edge
that can no longer be pushed; a key behind its own gate; a goal reachable without the intended trick.
