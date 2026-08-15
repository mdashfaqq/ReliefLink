"""Demo scenario: a heavy-rain flood across south and central Chennai.

All messages and people are fictional. Locations are real neighbourhoods so the
map is meaningful. The set deliberately includes duplicate reports of the same
incident, messages in Hindi and Tamil, and a range of urgencies.
"""

REQUESTS = [
    {"text": "We are trapped on the terrace, water rising fast. 6 people including 2 kids and my grandmother", "lat": 12.9812, "lon": 80.2183, "source": "whatsapp", "contact": "98400xxxx1"},
    {"text": "Family stuck on terrace near Velachery lake, water rising, children and old lady there", "lat": 12.9815, "lon": 80.2186, "source": "social"},
    {"text": "My father is unconscious and not breathing properly, need ambulance urgently", "lat": 13.0012, "lon": 80.2565, "source": "helpline", "contact": "98400xxxx2"},
    {"text": "Pregnant woman in labour, roads flooded, cannot reach hospital", "lat": 12.9110, "lon": 80.0700, "source": "helpline"},
    {"text": "வீட்டில் மாட்டிக்கொண்டோம், தண்ணீர் ஏறுகிறது, 4 பேர் இருக்கிறோம், முதியவர் இருக்கிறார்", "lat": 12.9380, "lon": 80.2050, "source": "sms"},
    {"text": "हम 5 लोग छत पर फंसे हैं, पानी बढ़ रहा है, बच्चे भी हैं", "lat": 12.9249, "lon": 80.1000, "source": "sms"},
    {"text": "Need drinking water for 30 people in the community hall, no water since yesterday", "lat": 13.0210, "lon": 80.2230, "source": "web"},
    {"text": "Need food and milk for baby, family of 4, not eaten since morning", "lat": 12.9640, "lon": 80.1980, "source": "web"},
    {"text": "Diabetic patient needs insulin, medicines finished, elderly man living alone", "lat": 13.0350, "lon": 80.2120, "source": "helpline"},
    {"text": "House wall collapsed, need a place to stay for family of 5, have blankets?", "lat": 12.9516, "lon": 80.1462, "source": "web"},
    {"text": "உணவு இல்லை, 10 பேர் பசியுடன் இருக்கிறோம், குழந்தைகள் உள்ளனர்", "lat": 12.9650, "lon": 80.2460, "source": "sms"},
    {"text": "Old man bedridden on ground floor, water entering the house, need to evacuate him", "lat": 13.0180, "lon": 80.2410, "source": "helpline"},
    {"text": "bedridden elderly person ground floor water coming in please evacuate", "lat": 13.0182, "lon": 80.2412, "source": "social"},
    {"text": "Snake bite! My son was bitten while wading through water", "lat": 12.9700, "lon": 80.2100, "source": "helpline"},
    {"text": "Need blankets and shelter for 12 people, our huts are damaged", "lat": 13.1667, "lon": 80.2667, "source": "web"},
    {"text": "Drinking water needed, 8 families, no clean water", "lat": 13.2146, "lon": 80.3203, "source": "web"},
    {"text": "Person with high fever and vomiting, need doctor", "lat": 13.0390, "lon": 80.1990, "source": "whatsapp"},
    {"text": "Stranded in car on the flooded road, water at waist level", "lat": 13.0418, "lon": 80.2341, "source": "helpline"},
    {"text": "Need food packets for 40 people at the relief camp", "lat": 12.9900, "lon": 80.2200, "source": "web"},
    {"text": "Dialysis patient missed session, needs transport to hospital", "lat": 12.9450, "lon": 80.1800, "source": "helpline"},
    {"text": "No one is injured but we need drinking water and rice", "lat": 13.0100, "lon": 80.2000, "source": "web"},
    {"text": "Electric shock risk, live wire fallen in flood water near the school, kids around", "lat": 13.0050, "lon": 80.2300, "source": "social"},
    {"text": "தண்ணீர் ஏறுகிறது, மொட்டை மாடியில் 3 பேர், படகு வேண்டும்", "lat": 12.9383, "lon": 80.2053, "source": "whatsapp"},
    {"text": "Need milk for infant and medicines for fever", "lat": 12.9600, "lon": 80.1500, "source": "web"},
]

VOLUNTEERS = [
    {"name": "Coast Guard Boat 1", "skills": ["rescue"], "lat": 12.9900, "lon": 80.2500, "capacity": 2},
    {"name": "Fisherfolk Boat - Karthik", "skills": ["rescue"], "lat": 12.9300, "lon": 80.1300, "capacity": 2},
    {"name": "NDRF Team Alpha", "skills": ["rescue", "medical"], "lat": 13.0300, "lon": 80.2300, "capacity": 2},
    {"name": "Dr. Meena (mobile clinic)", "skills": ["medical"], "lat": 12.9600, "lon": 80.2000, "capacity": 2},
    {"name": "108 Ambulance Unit 7", "skills": ["medical", "transport"], "lat": 13.0100, "lon": 80.2400, "capacity": 1},
    {"name": "Red Cross Supplies Van", "skills": ["supplies"], "lat": 13.0000, "lon": 80.2100, "capacity": 3},
    {"name": "Youth Volunteers - Tambaram", "skills": ["supplies", "transport"], "lat": 12.9250, "lon": 80.1100, "capacity": 2},
    {"name": "Mosque Relief Kitchen", "skills": ["supplies"], "lat": 13.0400, "lon": 80.2100, "capacity": 2},
    {"name": "Temple Trust Shelter Team", "skills": ["transport"], "lat": 13.1500, "lon": 80.2700, "capacity": 1},
    {"name": "Church Food Drive", "skills": ["supplies"], "lat": 13.2000, "lon": 80.3000, "capacity": 1},
]
