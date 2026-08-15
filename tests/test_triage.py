from app.triage import estimate_people, triage


def test_rooftop_rescue_is_critical():
    r = triage("We are trapped on the roof, water rising, grandmother is diabetic. 5 people")
    assert r.category == "rescue"
    assert "medical" in r.needs
    assert r.level == "CRITICAL"
    assert r.people == 5


def test_reasons_explain_the_score():
    r = triage("My father is unconscious, need ambulance")
    assert any("unconscious" in reason for reason in r.reasons)


def test_negated_condition_is_ignored():
    injured = triage("Two people injured, need water")
    not_injured = triage("No one is injured, need drinking water")
    assert "medical" in injured.needs
    assert "medical" not in not_injured.needs
    assert not_injured.category == "water"


def test_missing_resource_is_a_need_not_a_negation():
    # "no food" / "no medicine" means they NEED food/medicine.
    assert triage("we have no food").category == "food"
    assert triage("there is no medicine for my mother").category == "medical"
    assert triage("உணவு இல்லை").category == "food"


def test_hindi_rescue():
    r = triage("हम 5 लोग छत पर फंसे हैं, पानी बढ़ रहा है, बच्चे भी हैं")
    assert r.language == "hi"
    assert r.category == "rescue"
    assert r.level in ("CRITICAL", "HIGH")
    assert r.people == 5


def test_tamil_rescue():
    r = triage("வீட்டில் மாட்டிக்கொண்டோம், தண்ணீர் ஏறுகிறது, 3 பேர், முதியவர் இருக்கிறார்")
    assert r.language == "ta"
    assert r.category == "rescue"
    assert "elderly" in " ".join(r.reasons)


def test_tamil_negated_injury():
    r = triage("காயம் இல்லை, உணவு வேண்டும்")
    assert "medical" not in r.needs
    assert r.category == "food"


def test_urgency_ordering_makes_sense():
    drowning = triage("child drowning, water rising")
    hungry = triage("need food for 2 people")
    blankets = triage("need blankets")
    assert drowning.urgency > hungry.urgency > blankets.urgency


def test_corroboration_raises_urgency():
    base = triage("trapped in house with water entering")
    corroborated = triage("trapped in house with water entering", report_count=3)
    assert corroborated.urgency > base.urgency


def test_people_estimation():
    assert estimate_people("family of five stuck") == 5
    assert estimate_people("30 people in the hall") == 30
    assert estimate_people("help me") == 1


def test_unrecognized_message_goes_to_human_review():
    # Unknown wording must not silently sink to LOW: it's flagged for a coordinator.
    r = triage("please call me back")
    assert r.needs_review
    assert r.level == "MEDIUM"


def test_ml_fallback_handles_unseen_phrasing():
    r = triage("the tap water is contaminated")
    assert r.category == "water"
    assert r.needs_review
    assert any("ML model" in reason for reason in r.reasons)


def test_recognized_message_is_not_flagged():
    assert not triage("trapped on roof, water rising").needs_review
