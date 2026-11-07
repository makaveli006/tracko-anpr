# How accurate is the number plate system?

First measurement, 7 November 2026, on one video (`zoomed-in`, a 1 minute 50 second roadside recording).

## The result in one paragraph

When the system said it was sure of a number plate, it was right 15 times out of 16. It was sure about 15 of the 28 plates a person could read, and held back on most of the others rather than risk a wrong answer. The weak point is the vehicle count: it showed 59 vehicles when only 32 really passed, because parked vehicles were counted again and again. This is a first check on one short video, the most favourable of the ones we have, so these figures are an early indication and not a final score.

## The results

| Question | Result |
|---|---|
| When the system is sure of a number, how often is it right? | **15 of 16** (94%) |
| Of the plates a person can read, how many did it confirm correctly? | **15 of 28** (54%) |
| How many vehicles did it show, against how many really passed? | **59 shown, 32 real** |
| How often did it get the vehicle type right? | **27 of 32** (84%) |

Because the sample is small, the true figures could differ. Using the rule of thumb in our measurement procedure, the first figure could be anywhere from about 70% to 100%, and the second from about 35% to 73%.

### What happened to the 28 readable plates

| Outcome | Plates |
|---|---|
| Right, and the system was sure | 15 |
| Right, but the system was not sure enough to confirm it | 8 |
| Wrong, but the system did not confirm it | 3 |
| Wrong, and the system confirmed it | 1 |
| Nothing read at all | 1 |

So the system's reading was right on 23 of the 28 plates, and one wrong number was presented as confirmed: an M read as an H, on a two-row plate with a shadow across it. One wrong letter points to a different vehicle, so this counts as a full error.

### Why the vehicle count is too high

The system follows each vehicle through the video. When traffic passes in front of a parked vehicle, the system loses sight of it and treats it as a new vehicle when it reappears. One parked scooter was counted 19 times and another 5 times, which accounts for 22 of the 27 extra entries. This can be fixed, and the fix is planned for after the demo.

### Why the dashboard shows 27% and this page says about half

Both are correct, because they answer different questions.

- **27% on the dashboard** is 16 confirmed numbers out of the 59 entries the system counted. That 59 includes the repeat counts, and many of the entries had no readable plate.
- **About half on this page** is 15 correct numbers out of the 28 plates a person could read. It shows how the system did on the plates it had a fair chance of reading.

### Why the vehicle type was sometimes wrong

Two jeeps, a Mahindra Thar and a small red taxi were labelled Truck. An auto-rickshaw was also labelled Truck, because the system has only four types (car, motorcycle, bus, truck). Recognising more Indian vehicle types is already on the future work list.

## How we checked

1. We took all 59 vehicle entries the system produced for this video.
2. An AI assistant (Claude) read each plate from the saved images without seeing the system's answers, and those readings were saved before any comparison was made.
3. A team member then read 21 plates without seeing either the system's answer or the assistant's: the 11 hardest, plus 10 picked at random. All 10 random ones matched exactly. On the hard ones, the team member's reading was used.
4. Only then were the readings compared with the system's answers.

## What this does not tell us

- **It covers one video.** The other demo video (`clear`) and the newer upload (`kdy`) have not been checked.
- **It is our most favourable video.** `zoomed-in` was filmed closest to the traffic. The system confirmed a number for 27% of its vehicles, against 16% for `clear` and 2% for `kdy`, so other footage may well do worse.
- **Only 21 plates had a human check.** The other readings are the AI assistant's alone. A full human check would make the result stronger.
- **Vehicles the system missed completely were not counted.** Finding those needs someone to watch the whole video.
- **Results depend on the recording.** This video had good daylight and a clear view. Night, rain or a distant camera will give lower results.

The full method and working are in `ARCHITECTURE.md`, and the labels are in `labels/`.

---

# How to explain this to leadership

## The 30-second version

> "We tested the system against what a person can actually read on the plates. When it tells us it is sure of a number, it was right 15 times out of 16. One confirmed number was wrong, so a person should still check a number before anyone acts on it. When the system is unsure, it tells you. It is confirming about half of the readable plates today, and it had the right answer on many of the others but held back. The main thing we still need to fix is the vehicle count, because it counts parked vehicles more than once. This is an early test on one short video, the best of the ones we have, and we will test more before we put a firm number on it."

## The main points, in plain words

- **It is careful.** Think of a new employee who only signs off what they are certain of. They sign off fewer items, but you can trust what they sign.
- **One confirmed number was wrong.** One wrong letter points to a different vehicle, so a person should check a number before anyone acts on it.
- **A clear view matters.** A plate needs to be big and sharp in the picture. Our tests point to camera position as the biggest factor.
- **The count needs work.** Do not quote "total vehicles" as a true traffic count yet.
- **It is an early result.** Sixteen confirmed plates on our most favourable video is a small test, so present it as a promising start.

## Say this, not that

| Instead of | Say |
|---|---|
| "The system is 94% accurate." | "In our first test, it was right 15 times out of 16 when it was sure." |
| "Recognition coverage" | "How many vehicles we got a confirmed number for" |
| "Recall" | "How many readable plates it confirmed" |
| "Confidence score" | "How sure the system is" |
| "Unconfirmed" | "It read something, but was not sure enough to stand behind it" |
| "Track" or "track ID" | "One vehicle the system followed" |
| "Margin of error" | "It is a small test, so the true figure could be lower" |

Avoid saying "94% accurate" on its own. It sounds like a final score for all conditions, and this test cannot support that.

## Questions they may ask

**Can we trust the numbers it confirms?**
Mostly, but not blindly. 15 of 16 were right and one was wrong, so a person should check a number before anyone acts on it.

**Why doesn't it read every plate?**
Often the plate is too small, blurred or at an angle. In this test, it also held back on 8 plates it had read correctly, because it would rather say "not sure" than give a wrong number.

**Can it read more plates?**
We expect so. Placing the camera closer and in line with the traffic is the biggest improvement we know of. We can also review how strict the system is, once we have tested more footage.

**Why did it show 59 vehicles when there were 32?**
It counted parked vehicles again each time traffic passed in front of them. We know the cause and will fix it after the demo.

**The dashboard says 27%. Why are you saying about half?**
They measure different things. 27% is confirmed numbers out of everything the system counted, including repeat counts and vehicles with no readable plate. About half is correct numbers out of the plates a person could actually read.

**Why did you test on this video?**
It is the one with the clearest view of the plates, so it was the natural first test. It shows what the system can do in good conditions, and other videos may do worse. We will check those next.

**Is it ready for live use?**
Not yet. This is a proof of concept that works on recorded videos. The next steps are to fix the count, test more footage, and have people check a larger sample.

**What happens next?**
We will fix the parked-vehicle count, check the remaining videos, and repeat this test so that we can give a firm figure.
