from theme_tracker import ThemeTracker, classify_theme_status


def test_classify_theme_status_covers_new_continue_diverge_and_recede():
    assert classify_theme_status({"name": "AI", "heat_score": 70, "capital_score": 15})["status"] == "新发酵"

    previous = [{"name": "AI", "heat_score": 68, "consecutive_days": 2}]
    continuing = classify_theme_status(
        {"name": "AI", "heat_score": 72, "capital_score": 15, "leader_candidates": [1, 2]},
        previous,
    )
    diverging = classify_theme_status(
        {"name": "AI", "heat_score": 70, "capital_score": 15, "leader_candidates": [1]},
        previous,
    )
    receding = classify_theme_status(
        {"name": "AI", "heat_score": 45, "capital_score": 5, "leader_candidates": []},
        previous,
    )

    assert continuing["status"] == "延续"
    assert continuing["consecutive_days"] == 3
    assert diverging["status"] == "分化"
    assert receding["status"] == "退潮"
    assert receding["downgrade_reasons"]


def test_theme_tracker_saves_and_loads_history(tmp_path):
    class Result:
        generated_at = "2026-05-08 10:00:00"

        def to_dict(self):
            return {"generated_at": self.generated_at, "themes": [{"name": "AI", "heat_score": 70}]}

    tracker = ThemeTracker(tmp_path)
    path = tracker.save_history(Result())
    history = tracker.load_history()

    assert path.endswith("theme_radar_2026-05-08.json")
    assert history[0]["themes"][0]["name"] == "AI"
