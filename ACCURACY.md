# How accurate is the number plate system?

Two checks, 7 November 2026, on `kdy` (our main video, 64 seconds of a busy street) and `zoomed-in` (1 minute 50 seconds of a roadside, the best footage we have).

## The result in one paragraph

When the system said it was sure of a number plate, it was right 18 times out of 19 across the two videos. How many plates it can read depends heavily on the recording. On `zoomed-in` it confirmed 15 of the 28 plates a person could read. On `kdy` it confirmed only 3 of 125 vehicles, mainly because the footage is poor: a person could fully read only 10 plates out of 87 vehicles. The weak point is the vehicle count, which is still too high because parked vehicles are counted more than once. These are small, early checks, so treat them as an indication and not a final score.

## The results

| Question | `kdy` (main video) | `zoomed-in` (best footage) |
|---|---|---|
| When the system was sure of a number, how often was it right? | **3 of 3** | **15 of 16** (94%) |
| Of the plates a person could fully read, how many did it confirm correctly? | **3 of 10** | **15 of 28** (54%) |
| Vehicles shown, against how many really passed | **125 shown, 87 real** | **59 shown, 32 real** |
| How often was the vehicle type right? | **71 of 87** (82%) | **27 of 32** (84%) |

Because the samples are small, the true figures could differ. On `zoomed-in`, the first figure could be anywhere from about 70% to 100%, and the second from about 35% to 73%. Three confirmed numbers on `kdy` is too few to give a percentage at all.

The `zoomed-in` count of 59 is from before the parked-vehicle fix. That video has not been processed again; our test suggests it would show about 42.

### What happened to the readable plates

| Outcome | `kdy` (10 plates) | `zoomed-in` (28 plates) |
|---|---|---|
| Right, and the system was sure | 3 | 15 |
| Right, but not sure enough to confirm it | 1 | 8 |
| Wrong, but the system did not confirm it | 5 | 3 |
| Wrong, and the system confirmed it | 0 | 1 |
| Nothing read at all | 1 | 1 |

On `kdy` the system misread 5 readable plates, each by one character, and held back on all 5. That is its caution doing its job.

The one wrong confirmed number was on `zoomed-in`: an M read as an H, on a two-row plate with a shadow across it. One wrong letter points to a different vehicle, so it counts as a full error.

### Why so few plates are read on `kdy`

The main cause is the recording, not the software.

- **A person can't read most of them either.** Of 87 vehicles, 10 plates could be read in full and 13 in part. The other 64 could not be read at all. When a team member checked 29 of the best plates by eye, they could fully read only 9.
- **Most plates are too small.** About 6 in 10 of the plates examined were under 60 pixels wide, and none of those gave a confident reading.
- **Even large plates are smeared.** At 150 pixels or wider, only 35% of readings were confident, against 70 to 77% on our other videos. The characters look melted together. We don't know why: heavy processing in the phone is our best guess, but we have not proven it.
- **The camera moves during the clip,** which a fixed camera would not.

Processing the video again won't change this. A better recording would.

### Why the vehicle count is too high

The system follows each vehicle through the video. When traffic passes in front of a parked vehicle, it loses sight of it and treats it as a new vehicle when it reappears. On `zoomed-in`, one parked scooter was counted 19 times.

A first fix brought `kdy` down from 167 to 125, when 87 vehicles really passed. So it reduces the problem but does not remove it. It merged one real vehicle by mistake, a three-wheeler, and we kept the rule strict because looser settings lose more real vehicles.

### Why the dashboard's percentage looks different

The dashboard shows **2%** for `kdy` and **27%** for `zoomed-in`. Those figures are confirmed numbers out of every vehicle the system counted, including repeat counts and vehicles with no readable plate. For `kdy` that is 3 of 125.

The figures on this page compare confirmed numbers with the plates a person could actually read, which is a fairer test of the reading itself. Both are correct; they answer different questions.

### Why the vehicle type was sometimes wrong

On `kdy`, 13 of the 16 type errors were auto-rickshaws and similar three-wheelers, which the system can't name because it has only four types (car, motorcycle, bus, truck). On `zoomed-in`, two jeeps, a Mahindra Thar and a small red taxi were labelled Truck. Recognising more Indian vehicle types is on the future work list.

## How we checked

1. We took every vehicle entry the system produced: 167 on `kdy` and 59 on `zoomed-in`.
2. An AI assistant (Claude) read each plate from the saved images without seeing the system's answers, and those readings were saved before any comparison was made.
3. A team member then read plates without seeing the system's answer or the assistant's: 21 on `zoomed-in` and 29 on `kdy`. These were the hardest ones, plus some the assistant was sure of. On `zoomed-in`, all 10 sure ones matched exactly. On `kdy`, 3 of the 4 sure ones matched and the fourth could only be partly read.
4. Where the team member read a full number, that reading was used. Where a plate couldn't be confirmed by both, it was left out of the scoring.
5. Only then were the readings compared with the system's answers.

## What this does not tell us

- **The samples are small.** 19 confirmed numbers in all, and only 3 on `kdy`.
- **Only 50 plates had a human check.** The other readings are the AI assistant's alone. A full human check would make the result stronger.
- **`clear`, our third video, has not been checked.**
- **`zoomed-in` is our most favourable video.** It has the highest share of confirmed numbers: 27%, against 16% for `clear` and 2% for `kdy`.
- **Vehicles the system missed completely were not counted.** Finding those needs someone to watch the whole video.
- **The vehicle count of 87 is our own reading,** made by matching vehicles by appearance, so it may be slightly off.
- **An earlier run on `kdy` put a car's number on a bus.** That has been fixed and the figures here are from after the fix, but it shows this kind of error can happen.
- **Results depend on the recording.** Night, rain or a distant camera will give lower results.

The full method and working are in `ARCHITECTURE.md`, and the labels are in `labels/`.

---

# How to explain this to leadership

## The 30-second version

> "We tested the system against what a person can actually read on the plates. When it tells us it is sure of a number, it was right 18 times out of 19 across two videos. One was wrong, so a person should still check a number before anyone acts on it. On today's video it confirms only a few plates, and that is mostly the footage: a person could fully read only about one plate in nine. On clearer footage it confirmed about half of the readable plates. So the biggest gain is a better recording. We also still need to improve the vehicle count, because it counts parked vehicles more than once. These are early tests, and we will test more before we put a firm number on it."

## The main points, in plain words

- **It is careful.** Think of a new employee who only signs off what they are certain of. They sign off fewer items, but you can trust what they sign. On `kdy` it misread five plates and refused to sign off any of them.
- **It is not perfect.** One confirmed number was wrong. One wrong letter points to a different vehicle, so a person should check a number before anyone acts on it.
- **It can't read what can't be seen.** If a person can't read a plate in the video, the system won't either.
- **The recording matters most.** A plate needs to be big and sharp in the picture. `RECORDING_GUIDE.md` says how to film for this.
- **The count needs work.** Do not quote "total vehicles" as a true traffic count yet.
- **It is an early result.** Present it as a promising start.

## Say this, not that

| Instead of | Say |
|---|---|
| "The system is 94% accurate." | "In our tests, it was right 18 times out of 19 when it was sure." |
| "Recognition coverage" | "How many vehicles we got a confirmed number for" |
| "Recall" | "How many readable plates it confirmed" |
| "Confidence score" | "How sure the system is" |
| "Unconfirmed" | "It read something, but was not sure enough to stand behind it" |
| "Track" or "track ID" | "One vehicle the system followed" |
| "Margin of error" | "It is a small test, so the true figure could be lower" |

Avoid quoting a percentage on its own. It sounds like a final score for all conditions, and these tests can't support that.

## Questions they may ask

**The screen says 3 out of 125. Why so low?**
Mostly the footage. A person could fully read only 10 plates out of 87 vehicles here, and the system confirmed 3 of those. On clearer footage it confirmed about half of the readable plates.

**The dashboard says 2%. Why are you talking about half?**
They measure different things. The 2% is confirmed numbers out of everything the system counted, including repeat counts and vehicles with no readable plate. About half is what it managed on the plates a person could actually read, on our clearest video.

**Can we trust the numbers it confirms?**
Mostly, but not blindly. 18 of 19 were right and one was wrong, so a person should check a number before anyone acts on it.

**Why doesn't it read every plate?**
Often the plate is too small, smeared or at an angle. It also holds back when it isn't sure: on `zoomed-in` it held back on 8 plates it had read correctly, because it would rather say "not sure" than give a wrong number.

**Can it read more plates?**
We expect so. Placing the camera closer and in line with the traffic is the biggest improvement we know of, and a sharper recording would help. We can also review how strict the system is, once we have tested more footage.

**Why does it show 125 vehicles when there were 87?**
It counts parked vehicles again each time traffic passes in front of them. A first fix brought this down from 167. The count is better but still too high, so we don't quote it as a true traffic count yet.

**Why did you also test on `zoomed-in`?**
It was the quickest to check, and it has the best results of our videos, so it shows what the system can do with good footage. `kdy` shows what happens with poor footage. The third video has not been checked.

**Is it ready for live use?**
Not yet. This is a proof of concept that works on recorded videos. The next steps are to improve the count further, record better footage, test more of it, and have people check a larger sample.

**What happens next?**
We will keep improving the parked-vehicle count, test more footage, and repeat this check so that we can give a firm figure.
