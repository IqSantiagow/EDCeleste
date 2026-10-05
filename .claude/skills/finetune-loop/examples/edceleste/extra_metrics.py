"""EDCeleste metrics for eval_split.py --extra and build_dashboard.py: what matters when
the model presses game keys.

Only rows of kind "recording" (the pilot's real speech, test split) are scored here: the
honest test.
"""

NEEDS_LLM = "needs_llm"


def yes_probability(answer) -> float:
    return answer["noul"] if isinstance(answer, dict) else answer


def extra_metrics(rows: list) -> dict[str, str]:
    commands = talks = 0
    executed = executed_with_rule = wrong_extra_key = 0
    key_on_talk = key_on_talk_with_rule = 0
    for example, answers in rows:
        if example["kind"] != "recording" or example["split"] != "test":
            continue
        asked = {
            action
            for action, gold in example["gold"].items()
            if action != NEEDS_LLM and gold
        }
        pressed = {
            action
            for action, answer in answers.items()
            if action != NEEDS_LLM and yes_probability(answer) >= 0.5
        }
        llm_wanted = yes_probability(answers[NEEDS_LLM]) >= 0.5
        # app rule: when Celeste is needed, press nothing
        pressed_with_rule = set() if llm_wanted else pressed
        if asked:
            commands += 1
            executed += bool(pressed & asked)
            executed_with_rule += bool(pressed_with_rule & asked)
            wrong_extra_key += bool(pressed_with_rule - asked)
        else:
            talks += 1
            key_on_talk += bool(pressed)
            key_on_talk_with_rule += bool(pressed_with_rule)
    if not commands:
        return {}
    return {
        "recordings: command executed": f"{executed}/{commands}",
        "recordings: key pressed while only talking": f"{key_on_talk}/{talks}",
        "with rule 'needs_llm means no key': command "
        "executed": f"{executed_with_rule}/{commands}",
        "with rule: wrong extra key in a command": f"{wrong_extra_key}/{commands}",
        "with rule: key pressed while only talking": f"{key_on_talk_with_rule}/{talks}",
    }
