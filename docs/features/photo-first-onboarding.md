# Feature: photo-first onboarding with face recognition

**Status:** In v1 (approved 2026-10-13) · **Logged:** 2026-10-13 · **Owner:** Product Owner · **Author:** Designer (with Tech Lead and PM notes)

## Summary
A new Birthday Pi starts by learning the family from their photos. Family members upload photos from their phones. The Pi finds and groups faces, asks "Who is this?" once per person, and asks for the birthday as soon as a new person is named. On later imports, faces it recognises are labelled automatically.

## Why
- Typing 40 names and birthdays is a chore. Answering "Who is this?" about photos of the people you love is not.
- It fixes the frame-2 pain from the storyboard, *"Nothing tells her who is missing."* Once the Pi has seen a face, it knows that person has no birthday yet.
- The same photos feed the slideshow, including the "only their photos on their day" rule.

## Who does it
A family member on their phone during a visit, with Grandma beside them. Grandma signs off on the final list. All typing happens on the phone; the monitor only has a mouse.

## The flow

### 1. The monitor invites setup
A brand-new Pi has no people yet, so the monitor shows a welcome card and a QR code.

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│                    🎂  Birthday Pi                        │
│                                                          │
│               Let's meet your family.                    │
│                                                          │
│     ┌─────────┐   Scan with your phone to start,        │
│     │ ▓▓ ▓ ▓▓ │   or open                                │
│     │ ▓ ▓▓ ▓▓ │   http://birthdaypi.local:8080/setup    │
│     │ ▓▓ ▓ ▓ │                                           │
│     └─────────┘   Your phone must be on this Wi-Fi.     │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 2. Upload photos from the phone

```
┌─────────────────────────┐     ┌─────────────────────────┐
│ Birthday Pi        Setup│     │ Birthday Pi        Setup│
│─────────────────────────│     │─────────────────────────│
│                         │     │ Uploading…              │
│  Step 1 of 3            │     │ ████████████░░░░  96/128│
│  Add family photos      │     │                         │
│                         │     │ Looking for faces…      │
│  Pick photos with the   │     │ 46 faces · 11 people    │
│  family in them. Group  │     │                         │
│  shots are great.       │     │ You can start naming    │
│                         │     │ people now, and the     │
│  ┌───────────────────┐  │     │ rest will keep going.   │
│  │  📷 Choose photos │  │     │                         │
│  └───────────────────┘  │     │  ┌───────────────────┐  │
│                         │     │  │  Start naming  →  │  │
│  Photos stay on this    │     │  └───────────────────┘  │
│  Pi. Nothing is sent    │     │                         │
│  to the internet.       │     │  + Add more photos      │
└─────────────────────────┘     └─────────────────────────┘
```

The monitor mirrors progress ("128 photos · 46 faces found") so Grandma can follow along.

### 3. "Who is this?" once per person
Faces are grouped by person, and the largest groups are asked about first. A card shows up to six face crops.

```
┌─────────────────────────┐     ┌─────────────────────────┐
│ Step 2 of 3   Person 3/11│    │ Not all the same person?│
│─────────────────────────│     │─────────────────────────│
│ Who is this?            │     │ Tap the faces that      │
│ Seen in 14 photos       │     │ AREN'T this person.     │
│                         │     │                         │
│  ┌───┐ ┌───┐ ┌───┐      │     │  ┌───┐ ┌───┐ ┌───┐      │
│  │ ☺ │ │ ☺ │ │ ☺ │      │     │  │ ☺ │ │ ☺ │ │ ✕ │      │
│  └───┘ └───┘ └───┘      │     │  └───┘ └───┘ └───┘      │
│  ┌───┐ ┌───┐ ┌───┐      │     │  ┌───┐ ┌───┐ ┌───┐      │
│  │ ☺ │ │ ☺ │ │ ☺ │      │     │  │ ☺ │ │ ✕ │ │ ☺ │      │
│  └───┘ └───┘ └───┘      │     │  └───┘ └───┘ └───┘      │
│                         │     │                         │
│ Name ┌───────────────┐  │     │  ┌───────────────────┐  │
│      │ Mi│           │  │     │  │       Done        │  │
│      └───────────────┘  │     │  └───────────────────┘  │
│   ▸ Mia (already added) │     └─────────────────────────┘
│   ▸ Add "Mi…" as new    │
│                         │
│ Not all the same person?│
│ Not family · Skip       │
│ Not a person (pet etc.) │
└─────────────────────────┘
```

- Typing suggests people already named, so the same person found in two groups gets merged instead of duplicated.
- **Not family** ignores that face group from then on (waiters, strangers in the background).
- **Not a person** ignores a group that isn't a human face at all, such as a pet. The face detector can't reliably tell pets from people: in the 2026-10-13 test a dog scored 0.86–0.87 face confidence, higher than 6 of 37 human faces, so no cut-off can filter it out. The 3-photo rule stops most pets being asked about; this button handles the rest. (Pets with birthdays are a future idea: `pets-as-family.md`.)
- **Skip** comes back to it later.

### 4. New person → ask their dates there and then

```
┌─────────────────────────┐     ┌─────────────────────────┐
│ Mia                ☺    │     │ Mia                ☺    │
│─────────────────────────│     │─────────────────────────│
│ When is Mia's birthday? │     │ Does Mia have a partner │
│                         │     │ we should celebrate an  │
│ Month ┌──────────────┐  │     │ anniversary with?       │
│       │ March      ▾ │  │     │                         │
│       └──────────────┘  │     │ ┌───────────────────┐   │
│ Day   ┌──────────────┐  │     │ │ Pick a person   ▾ │   │
│       │ 14         ▾ │  │     │ └───────────────────┘   │
│       └──────────────┘  │     │ Anniversary             │
│ Year  ┌──────────────┐  │     │ ┌───────┐ ┌────┐        │
│ (opt) │ 2019       ▾ │  │     │ │ Month▾│ │Day▾│        │
│       └──────────────┘  │     │ └───────┘ └────┘        │
│ Mia turns 7 this year.  │     │                         │
│                         │     │  ┌───────────────────┐  │
│  ┌───────────────────┐  │     │  │       Save        │  │
│  │       Save        │  │     │  └───────────────────┘  │
│  └───────────────────┘  │     │      No / not now       │
│   I'll add it later     │     └─────────────────────────┘
└─────────────────────────┘
```

- Month and day are required; the year is optional. With a year, the screen can say "Mia turns 7."
- "I'll add it later" puts Mia on the **Who's missing a birthday?** list.
- The anniversary step is optional and only shown for adults (PM question 4).

### 5. Who's missing, and Grandma signs off

```
┌─────────────────────────┐     ┌─────────────────────────┐
│ Step 3 of 3             │     │ Here's your family      │
│─────────────────────────│     │─────────────────────────│
│ Who's missing a         │     │ ☺ Grandma     Jun 2     │
│ birthday?               │     │ ☺ Mia         Mar 14    │
│                         │     │ ☺ Leo         Aug 30    │
│ ☺ Leo           Add  →  │     │ ☺ Dana & Sam  ♥ Sep 9   │
│ ☺ Aunt Rosa     Add  →  │     │ ☺ Aunt Rosa   Nov 21    │
│ ☺ Sam           Add  →  │     │   … 6 more              │
│                         │     │                         │
│ 2 more people to name   │     │ Grandma, does this      │
│   Keep naming  →        │     │ look right?             │
│                         │     │                         │
│  ┌───────────────────┐  │     │  ┌───────────────────┐  │
│  │  Finish for now   │  │     │  │   Looks right ✓   │  │
│  └───────────────────┘  │     │  └───────────────────┘  │
└─────────────────────────┘     │     Change something    │
                                └─────────────────────────┘
```

After setup, the "Who's missing" list stays on the phone home page until it's empty. The monitor can also show a gentle note, "3 people still need a birthday."

### 6. Later imports recognise people

```
┌─────────────────────────┐
│ 24 new photos added     │
│─────────────────────────│
│ ✓ Recognised            │
│   Mia ×6 · Leo ×4 ·     │
│   Grandma ×3            │
│                         │
│ Is this Leo?            │
│  ┌───┐                  │
│  │ ☺ │  ┌─────┐ ┌────┐  │
│  └───┘  │ Yes │ │ No │  │
│         └─────┘ └────┘  │
│                         │
│ New face (in 3 photos)  │
│  ┌───┐  Who is this? →  │
│  │ ☺ │                  │
│  └───┘                  │
└─────────────────────────┘
```

- Confident matches are labelled silently, but only for people with at least 3 verified photos.
- Unsure matches ask yes/no. Each "Yes" teaches the Pi, which helps most with children, whose faces change.
- Every photo can be corrected from the person's page ("Not Mia").

## Design rules
- **Ask per person, never per photo.**
- **Biggest groups first.** The people in the most photos matter most.
- **Three photos to confirm.** A face group is only offered as "Who is this?" once it appears in at least 3 photos, and naming it verifies those photos.
- **Three verified photos to recognise.** The Pi never auto-identifies someone until they have at least 3 verified photos. Before that, every match is asked as "Is this Leo?".
- **Ignore the noise.** Very small faces aren't asked about. People in fewer than 3 photos can still be tagged by hand.
- **Never block.** Every step can be skipped and finished later; the slideshow works even if no one is named.
- **Easy to undo.** Merge, split, rename and "Not this person" are always available.
- **Large touch targets.** Grandma may do this on her own tablet, and the monitor may become a touchscreen.

## How it connects to the rest of Birthday Pi
- **On someone's day,** the slideshow shows only photos with that person in them, including group photos. A slow zoom towards their face makes a group photo read as *their* photo.
- **On other days,** all photos cycle (current rule).
- **Reminders** come from the birthdays and anniversaries collected here.

## Privacy and safety
- Photos and face data never leave the Pi. No cloud face recognition.
- Face data includes children. **Remove person** deletes their face data and face crops, not just the name, and lets you choose whether to also delete their photos.
- Some places regulate biometric data. Because this is a private family device, the risk is low, but the setup screen should say plainly what is stored and how to remove it.
- Anyone on the home Wi-Fi can reach setup. See the open question on who can edit.

## Tech Lead notes
- **Models:** OpenCV YuNet for finding faces (under 1 MB) and SFace for matching them (about 37 MB), both running on the Pi's processor. InsightFace "buffalo_s" is the alternative if accuracy isn't good enough.
- **Grouping:** clustering on face embeddings, with a confidence threshold for auto-labelling. Each person's verified faces become their reference set; auto-labelling is off for anyone with fewer than 3 verified faces.
- **Manual tagging:** "Who's in this photo?" on any photo, as the fallback when recognition misses or is wrong. Hand-tagged faces count as verified.
- **Throughput (estimate, to be measured):** about 1,000 photos in 5–15 minutes, using a few hundred MB of RAM during import. Import runs as a background job so the screen stays responsive.
- **Storage:** photos are resized to screen size on import (about 0.5 GB per 1,000 photos). We keep the face crops and embeddings, not the full-size originals.
- **Formats:** iPhone HEIC photos need converting. Duplicate photos are detected and skipped.
- **Resource limits:** the import worker gets its own container memory limit so it can never starve the kiosk.

## Open questions for the Product Owner
1. **Who does the first setup?** Assumed: a family member on their phone, with Grandma.
2. **Photo sources for v1:** phone upload only? (Google Photos and iCloud need the internet; they would be later integrations.)
3. ~~**Which faces to ask about**~~ Decided 2026-10-13: confirm a person with at least 3 photos; never auto-identify anyone with fewer than 3 verified photos.
4. **Anniversaries:** capture them while naming people (pair partners), or as a separate step?
5. ~~**Fallback**~~ Decided 2026-10-13: tagging "who's in this photo" by hand is acceptable.
6. ~~**Version 1 scope**~~ Decided 2026-10-13: in v1.
