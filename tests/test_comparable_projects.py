from __future__ import annotations

from batteryhack.comparable_projects import TOP_COMPARABLE_PROJECTS, comparable_projects_table


def test_top_comparable_projects_are_ranked_and_scored() -> None:
    assert len(TOP_COMPARABLE_PROJECTS) == 3
    ranks = [project.rank for project in TOP_COMPARABLE_PROJECTS]
    scores = [project.similarity_score for project in TOP_COMPARABLE_PROJECTS]

    assert ranks == [1, 2, 3]
    assert scores == sorted(scores, reverse=True)
    assert min(scores) >= 80


def test_comparable_project_metadata_has_actionable_mapping() -> None:
    for project in TOP_COMPARABLE_PROJECTS:
        assert project.url.startswith("https://github.com/")
        assert project.reusable_patterns
        assert project.embedded_decisions
        assert project.caution


def test_comparable_projects_table_is_ui_friendly() -> None:
    rows = comparable_projects_table()

    assert len(rows) == 3
    assert {"project", "url", "similarity_score", "what_we_can_get"}.issubset(rows[0])
