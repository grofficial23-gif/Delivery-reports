import pytest
from datetime import date, timedelta
from delivery_reports.repository import Note, Project
from delivery_reports.services.draft_builder import build_weekly_summary

def test_build_weekly_summary():
    director_id = 999111
    employee_id = 999222
    team_name = "Team Alpha"

    projects = [
        Project(id=101, owner_user_id=director_id, name="Super Project 1", manager_name="", lead_name="", jira_base_url="", aliases=[], is_special_control=False),
        Project(id=102, owner_user_id=director_id, name="Super Project 2", manager_name="", lead_name="", jira_base_url="", aliases=[], is_special_control=False)
    ]
    
    notes = [
        Note(
            id=1,
            note_date=date.today() - timedelta(days=1),
            user_id=director_id,
            source="text",
            raw_text="test",
            project_id=101,
            manager_name="",
            lead_name="",
            epic=None,
            status_text=None,
            done_text="- Completed task A",
            plan_text="",
            risk_text=None,
            jira_links=[],
            needs_review=False
        ),
        Note(
            id=2,
            note_date=date.today() - timedelta(days=2),
            user_id=employee_id,
            source="text",
            raw_text="test",
            project_id=101,
            manager_name="",
            lead_name="",
            epic=None,
            status_text=None,
            done_text="- Completed task B",
            plan_text="- Will do C",
            risk_text=None,
            jira_links=[],
            needs_review=False
        ),
        Note(
            id=3,
            note_date=date.today() - timedelta(days=3),
            user_id=employee_id,
            source="text",
            raw_text="test",
            project_id=102,
            manager_name="",
            lead_name="",
            epic=None,
            status_text=None,
            done_text="- Investigated DB issue",
            plan_text="",
            risk_text="- Need DBA access",
            jira_links=[],
            needs_review=False
        )
    ]

    end_date = date.today()
    start_date = end_date - timedelta(days=7)

    summary = build_weekly_summary(
        start_date=start_date,
        end_date=end_date,
        notes=notes,
        projects=projects,
        team_name=team_name
    )

    # Validate output
    assert "Weekly Summary: Team Alpha" in summary or "Super Project 1" in summary
    assert "Super Project 1" in summary
    assert "Super Project 2" in summary
    assert "Completed task A" in summary
    assert "Completed task B" in summary
    assert "Investigated DB issue" in summary
    assert "Need DBA access" in summary
