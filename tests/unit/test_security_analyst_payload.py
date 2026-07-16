from birre.domain.security_analyst.payload import build_jira_action_payload


def test_build_jira_action_payload_preserves_action_evidence_and_hides_batch() -> None:
    grouped = {
        "groups": {
            "company-1": {
                "name": "Acme",
                "primary_domain": "acme.example",
                "current_rating": 650,
                "triggers": [
                    {
                        "alert_guid": "alert-1",
                        "alert_date": "2026-07-01",
                        "start_date": "2026-06-30",
                        "severity": "high",
                        "trigger": "Rating changed",
                        "raw_alert": {"guid": "alert-1", "kind": "rating"},
                        "source_metadata": {"page_index": 0},
                    }
                ],
            }
        },
        "metadata": {"warnings": ["alert_page_cap_reached"]},
    }
    candidates = {
        "action_candidates": [
            {
                "company_guid": "company-1",
                "priority": 2,
                "priority_level": 3,
                "priority_score": 5,
                "eligible": True,
                "rating_movement": {
                    "rating_before": 800,
                    "rating_after": 650,
                    "drop": 150,
                    "source": "company_history",
                },
                "missing_data": ["jira_project"],
            }
        ],
        "filtered_candidates": [
            {
                "company_guid": "company-2",
                "eligible": False,
                "filter_reason": "priority_filtered",
            }
        ],
    }

    result = build_jira_action_payload(
        grouped,
        candidates,
        warnings=["category_ambiguous"],
    )

    assert set(result) == {"action_items", "metadata"}
    assert "internal_batch" not in result
    item = result["action_items"][0]
    assert item["company_guid"] == "company-1"
    assert item["correlation_key"] == "company-1"
    assert (item["company_name"], item["primary_domain"], item["current_rating"]) == (
        "Acme",
        "acme.example",
        650,
    )
    assert item["alerts"] == [
        {
            "alert_guid": "alert-1",
            "event_date": "2026-07-01",
            "seen_at": "2026-06-30",
            "severity": "high",
            "trigger": "Rating changed",
            "raw_evidence_reference": {"guid": "alert-1", "kind": "rating"},
        }
    ]
    assert item["proposed_jira_body"] == {
        "rating_before": 800,
        "rating_after": 650,
        "rating_drop": 150,
        "movement_source": "company_history",
        "current_rating": 650,
    }
    assert item["priority_score"] == 5
    assert item["priority_level"] == 3
    assert item["eligible"] is True
    assert item["missing_data_flags"] == ["jira_project"]
    assert item["warning_codes"] == []
    assert result["metadata"] == {
        "warnings": ["alert_page_cap_reached", "category_ambiguous"],
        "missing_data_flags": ["jira_project"],
        "filtered_candidates": candidates["filtered_candidates"],
    }
