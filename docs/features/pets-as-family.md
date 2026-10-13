# Future idea: pets as family

**Status:** Parked for consideration after v1 · **Logged:** 2026-10-13 · **Owner:** Product Owner

## The idea
For many grandparents, the dog or cat *is* family. Birthday Pi could let pets have a name, a birthday (or "gotcha day") and their own photos on their day, just like people.

## Where it came from
In the 2026-10-13 face-recognition test, the Product Owner's dog was detected as a face and grouped like a person. For v1 we ignore pets with a **Not a person** button (see `photo-first-onboarding.md`). This idea turns that moment into a feature.

## How it could work
- On a "Who is this?" card, a **This is a pet** option next to "Not a person". It asks for a name, an optional birthday or adoption day, and a type (dog, cat, other).
- Pets get reminders too, probably only a day-of one ("It's Biscuit's birthday! 🐾"), since a gift or card two weeks out is less likely.
- On their day, the slideshow shows their photos, the same rule as for people.

## Things to work out
- **Recognising the same pet again.** The face-matching model is trained on human faces, so it may not reliably tell one dog from another. Options: tag pet photos by hand (the v1 fallback), or add a pet-specific model later.
- **Which reminders pets get:** day-of only, or the full gift / card / call set?
- **Memorial days:** pets don't live as long as people. Should Birthday Pi handle "remembering" a pet that has died, gently, or simply allow removing them?
- **Size budget:** a pet detector or pet-matching model adds memory and image size on the Pi.
