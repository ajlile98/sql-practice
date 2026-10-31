"""Read-only learning statistics derived from current metadata and saved checks."""

from collections import Counter, defaultdict
from statistics import median

from sql_practice.exercises import Categories, Exercise, exercise_statuses, matching_exercises


def effort_metrics(checks: list[dict]) -> dict:
    histories = defaultdict(list)
    for check in checks:
        histories[check["exercise"]].append(check)
    solve_checks = []
    solve_failures = []
    solve_sessions = []
    review_exercises = []
    assistance_questions = 0
    unsolved_checks = 0
    for identifier, history in histories.items():
        first_solve = next(
            (
                index + 1
                for index, check in enumerate(history)
                if check["passed"] and not check["assisted"]
            ),
            None,
        )
        learning_checks = history[:first_solve] if first_solve is not None else history
        assisted = any(check["assisted"] for check in learning_checks)
        assistance_questions += int(assisted)
        if first_solve is None:
            unsolved_checks += len(history)
            continue
        failures = sum(not check["passed"] for check in learning_checks)
        solve_checks.append(first_solve)
        solve_failures.append(failures)
        if all(
            isinstance(check.get("session"), str) and check["session"].strip()
            for check in learning_checks
        ):
            solve_sessions.append(len({check["session"] for check in learning_checks}))
        if failures or assisted:
            review_exercises.append(identifier)
    return {
        "solved_sample": len(solve_checks),
        "median_checks_to_solve": median(solve_checks) if solve_checks else None,
        "median_failures_to_solve": median(solve_failures) if solve_failures else None,
        "sessions_sample": len(solve_sessions),
        "median_sessions_to_solve": median(solve_sessions) if solve_sessions else None,
        "assistance_questions": assistance_questions,
        "assistance_percent": 100 * assistance_questions / len(histories) if histories else None,
        "review_questions": len(review_exercises),
        "review_exercises": sorted(review_exercises),
        "unsolved_checks": unsolved_checks,
    }


def metrics(identifiers: set[str], attempts: list[dict]) -> dict:
    checks = [item for item in attempts if item["exercise"] in identifiers]
    states = Counter(exercise_statuses(checks).values())
    first = {}
    for check in checks:
        first.setdefault(check["exercise"], check)
    first_passes = sum(item["passed"] and not item["assisted"] for item in first.values())
    available = len(identifiers)
    attempted = len(first)
    return {
        "available": available,
        "attempted": attempted,
        "solved": states["SOLVED"],
        "assisted_only": states["ASSISTED"],
        "needs_work": states["ATTEMPTED"],
        "unattempted": available - attempted,
        "coverage_percent": 100 * states["SOLVED"] / available if available else None,
        "first_try_passes": first_passes,
        "first_try_percent": 100 * first_passes / attempted if attempted else None,
        "limited_evidence": attempted < 5,
        "attempts": len(checks),
        "failed_checks": sum(not item["passed"] for item in checks),
        "assisted_checks": sum(bool(item["assisted"]) for item in checks),
        "assisted_passes": sum(item["passed"] and item["assisted"] for item in checks),
        **effort_metrics(checks),
    }


def recommendations(groups: dict) -> list[dict]:
    ordered = sorted(
        groups.items(),
        key=lambda pair: (
            -(pair[1]["needs_work"] + pair[1]["assisted_only"]),
            -pair[1]["review_questions"],
            -pair[1]["unattempted"],
            pair[0],
        ),
    )
    result = []
    for identifier, group in ordered[:3]:
        revisit = group["needs_work"] + group["assisted_only"]
        if revisit:
            action, reason = (
                "revisit",
                f"{revisit} attempted or assisted-only questions need an independent pass",
            )
        elif group["review_questions"]:
            action, reason = (
                "review",
                (
                    f"{group['review_questions']} solved questions had failed checks or assistance "
                    "before independent success; retry intentionally with --exercise ID"
                ),
            )
        elif group["unattempted"]:
            action, reason = "explore", f"{group['unattempted']} questions have not been checked"
        elif not group["available"]:
            action, reason = (
                "generate",
                "No exercises available; ask Copilot to generate validated material",
            )
        else:
            action, reason = (
                "generate",
                "All available questions solved; broaden filters or request new material",
            )
        result.append(
            {
                "category": identifier,
                "label": group["label"],
                "action": action,
                "reason": reason,
                "exercises": group["review_exercises"] if action == "review" else [],
            }
        )
    return result


def learning_progress(
    bank: list[Exercise],
    attempts: list[dict],
    categories: Categories,
    *,
    engine=None,
    difficulty=None,
    category=None,
    topic=None,
) -> dict:
    known_tags = {tag for item in bank for tag in item.tags}
    mapped_tags = {tag for item in categories.entries for tag in item.tags}
    if topic is not None and topic not in known_tags | mapped_tags | set(categories.context_tags):
        raise ValueError(f"Unknown topic: {topic}")
    selected = matching_exercises(
        bank,
        categories=categories,
        engine=engine,
        difficulty=difficulty,
        category=category,
        topic=topic,
    )
    identifiers = {item.id for item in selected}
    bank_ids = {item.id for item in bank}
    engine_attempts = [item for item in attempts if engine is None or item["engine"] == engine]
    scoped = [
        item
        for item in engine_attempts
        if not (category or topic or difficulty) or item["exercise"] in identifiers
    ]
    legacy = defaultdict(lambda: {"attempts": 0, "passes": 0, "assisted_passes": 0})
    for item in scoped:
        for tag in item["tags"]:
            legacy[tag]["attempts"] += 1
            legacy[tag]["passes"] += int(item["passed"] and not item["assisted"])
            legacy[tag]["assisted_passes"] += int(item["passed"] and item["assisted"])
    entries = [item for item in categories.entries if category is None or item.id == category]
    groups = {
        item.id: {
            "label": item.label,
            "description": item.description,
            "tags": list(item.tags),
            **metrics(
                {
                    question.id
                    for question in selected
                    if set(item.tags).intersection(question.tags)
                },
                scoped,
            ),
        }
        for item in entries
    }
    report_tags = {tag for item in selected for tag in item.tags} | {
        tag for item in entries for tag in item.tags
    }
    topic_progress = {
        tag: {"label": tag, **metrics({item.id for item in selected if tag in item.tags}, scoped)}
        for tag in sorted({topic} if topic is not None else report_tags)
    }
    return {
        "total_attempts": len(scoped),
        "topics": dict(legacy),
        "overall": metrics(identifiers, scoped),
        "categories": groups,
        "topic_progress": topic_progress,
        "recommendations": recommendations(groups),
        "unmapped_tags": sorted(known_tags - mapped_tags - set(categories.context_tags)),
        "archived_attempts": sum(item["exercise"] not in bank_ids for item in engine_attempts),
        "scope": {"engine": engine, "difficulty": difficulty, "category": category, "topic": topic},
        "basis": "Current exercise tags and categories; unique questions, best recorded status. Categories overlap.",
    }
