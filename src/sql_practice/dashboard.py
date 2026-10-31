"""Read-only Streamlit view of the shared learning-progress report."""

import pandas as pd
import streamlit as st

from sql_practice import cli
from sql_practice.exercises import ENGINES


def percent(value):
    return "N/A" if value is None else f"{value:.0f}%"


def sample(value, count):
    return "N/A (n=0)" if value is None else f"{value:g} (n={count})"


def show_report(report, view):
    overall = report["overall"]
    columns = st.columns(4)
    columns[0].metric("Independently solved", f"{overall['solved']} / {overall['available']}")
    columns[1].metric("First-check success", percent(overall["first_try_percent"]))
    columns[2].metric("Graded checks", overall["attempts"])
    columns[3].metric("Unfinished questions", overall["needs_work"] + overall["assisted_only"])
    if overall["limited_evidence"]:
        st.warning(
            f"Limited evidence: {overall['attempted']} distinct questions attempted (fewer than 5)."
        )
    st.caption(report["basis"])
    groups = report["categories"] if view == "Categories" else report["topic_progress"]
    st.subheader("Completion by skill")
    if not overall["available"]:
        st.info("No exercises match this scope. This is a content gap, not a weakness.")
    elif groups:
        completion = pd.DataFrame(
            [
                {
                    "Skill": group["label"],
                    "Solved": group["solved"],
                    "Assisted only": group["assisted_only"],
                    "Needs work": group["needs_work"],
                    "New": group["unattempted"],
                }
                for group in groups.values()
            ]
        ).set_index("Skill")
        st.bar_chart(
            completion,
            horizontal=True,
            stack=True,
            color=["#16836c", "#bc7a15", "#c74c55", "#b3b8bd"],
        )
    st.subheader("Effort to first independent pass")
    if not overall["attempted"]:
        st.info("No graded attempts in this scope.")
    else:
        effort = []
        for group in [{"label": "Overall", **overall}, *groups.values()]:
            if not group["attempted"]:
                continue
            effort.append(
                {
                    "Skill": group["label"],
                    "Checks": sample(group["median_checks_to_solve"], group["solved_sample"]),
                    "Failures": sample(group["median_failures_to_solve"], group["solved_sample"]),
                    "Checked sessions": sample(
                        group["median_sessions_to_solve"], group["sessions_sample"]
                    ),
                    "Questions with help": f"{group['assistance_questions']} / {group['attempted']}",
                    "Historical review": group["review_questions"],
                }
            )
        st.dataframe(pd.DataFrame(effort), hide_index=True, width="stretch")
        st.caption(
            "Medians include independently solved questions only, stopping at their first independent pass. "
            "Sessions count checked session IDs, not time. Help reflects recorded hints and solutions only."
        )
        if overall["solved_sample"] < 5:
            st.warning(
                f"Limited solved sample: n={overall['solved_sample']}. Effort is not a mastery score."
            )
        st.caption(
            f"Ongoing checks on questions without an independent pass: {overall['unsolved_checks']}."
        )
    st.subheader("Practice priorities")
    for recommendation in report["recommendations"]:
        st.markdown(f"**{recommendation['label']}**: {recommendation['reason']}")
        if recommendation["exercises"]:
            st.markdown("Historical review: " + ", ".join(recommendation["exercises"]))
    st.caption(
        "Historical review reflects earlier failures or help, not proof of a current weakness."
    )
    if report["unmapped_tags"]:
        st.warning("Unmapped topics: " + ", ".join(report["unmapped_tags"]))
    if report["archived_attempts"]:
        st.caption(f"Archived checks outside the current bank: {report['archived_attempts']}.")


def main():
    st.set_page_config(page_title="SQL Practice | Progress", page_icon=":bar_chart:", layout="wide")
    st.title("SQL Practice")
    st.caption("Learning progress")
    try:
        practice = cli.service()
        with st.sidebar:
            st.header("Scope")
            engine = st.selectbox(
                "Engine",
                [None, *ENGINES],
                key="engine",
                format_func=lambda value: value or "All engines",
            )
            difficulty = st.selectbox(
                "Difficulty",
                [None, "intermediate", "advanced"],
                key="difficulty",
                format_func=lambda value: value or "All difficulties",
            )
            labels = {item.id: item.label for item in practice.categories.entries}
            category = st.selectbox(
                "Category",
                [None, *labels],
                key="category",
                format_func=lambda value: labels[value] if value else "All categories",
            )
            tags = sorted(
                {tag for item in practice.bank for tag in item.tags}
                | {tag for item in practice.categories.entries for tag in item.tags}
                | set(practice.categories.context_tags)
            )
            topic = st.selectbox(
                "Topic", [None, *tags], key="topic", format_func=lambda value: value or "All topics"
            )
            st.button("Refresh", icon=":material/refresh:")
        report = practice.progress(
            engine=engine, difficulty=difficulty, category=category, topic=topic
        )
    except (ValueError, KeyError, OSError):
        st.error("Could not load local progress. Check the exercise and category files.")
        return
    view = st.radio("Breakdown", ["Categories", "Topics"], horizontal=True)
    show_report(report, view)


if __name__ == "__main__":
    main()
