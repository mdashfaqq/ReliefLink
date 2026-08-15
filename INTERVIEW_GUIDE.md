# Interview guide: questions you should be able to answer

Read the code before any interview. These are the questions ReliefLink invites, with the reasoning behind each answer. Explain them in your own words; don't recite these.

**1. Why a lexicon plus a small classifier instead of a big language model?**
Disasters knock out connectivity. The core triage runs offline, instantly, on a laptop in a control room. It's also explainable: every urgency point traces to a phrase, so a coordinator can trust or override it. A language model could be an optional layer, but not the foundation.

**2. Why did you add a "safety floor"?**
The first evaluation showed 41% recall on critical messages. The two kinds of error aren't symmetric: sending a boat to a non-critical case wastes minutes, while missing a drowning risk can cost a life. So any explicit threat to life guarantees at least HIGH.

**3. Your development accuracy is 100% but held-out is 91%. Isn't that a problem?**
It's expected, and it's why the held-out set exists. I tuned on the development set, so its score is optimistic by construction. The held-out set was labeled before being run and never used for tuning. The gap tells you how much the lexicon overfits, and it's the reason the ML fallback exists.

**4. How does negation work across languages?**
English puts the negator before the phrase ("no one is injured"); Hindi and Tamil usually put it after ("घायल नहीं", "காயம் இல்லை"). The code checks a window before the match for English negators and after it for Hindi/Tamil ones. Resource words are exempt, because "no food" means they *need* food.

**5. Why the Hungarian algorithm? Isn't greedy good enough?**
Greedy commits early. If the nearest boat takes a mild case, a critical case may have nobody left. The Hungarian algorithm finds the global optimum over all pairs in O(n³), which is fast for hundreds of requests. The 200-scenario simulation shows +29.8 points in critical requests served.

**6. How do you handle volunteer capacity?**
A volunteer with capacity 3 becomes 3 rows (slots) in the cost matrix. That turns a capacitated problem into a standard one-to-one assignment.

**7. What does DISTANCE_WEIGHT = 4 mean?**
1 km of travel is worth 4 urgency points. It's a policy choice, not a fact. In practice coordinators should set it, and a natural extension is to expose it in the dashboard.

**8. Why character n-grams for duplicate detection?**
Messages mix scripts, typos and transliteration. Character n-grams need no tokenizer and no model download, and they work for Tamil and Hindi as well as English. Spatial and time constraints stop unrelated but similar-sounding requests from merging.

**9. What stops low-priority requests from waiting forever?**
Aging: open requests gain up to 15 urgency points over time. It's the same idea as preventing starvation in an operating-system scheduler.

**10. What would you change for a real deployment?**
Evaluate on real anonymized messages with coordinator-labeled ground truth; use road-network routing that excludes flooded roads; move to Postgres/PostGIS; add authentication, audit logs and data retention rules for phone numbers and locations.
