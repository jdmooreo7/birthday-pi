# Future feature: family tree that fills in

**Status:** Backlog (after v0.1) · **Logged:** 2026-10-14 · **Owner:** Product Owner

## The idea
A screen on Grandma's phone with an illustrated tree. Each person in the family is a leaf. A person with a birthday is a full, coloured leaf; a person still missing one is a pale bud. When everyone has a birthday, the tree animates to full bloom. Grandma can see at a glance whether anything is missing, without reading a list.

## Why
The "who's missing a birthday" list works, but it's text. A tree that visibly fills up is quicker to read, feels like progress rather than a chore, and gives family members a reason to finish ("one more leaf!").

## Designer notes
- Tapping a bud opens that person's page to add the birthday, so the tree is also the way to fix the gap.
- Animate gently: a leaf unfurls when a birthday is saved, and blossoms appear when the tree is complete. Respect the phone's "reduce motion" setting.
- Keep it readable for Grandma: large leaves, names on tap, a short caption ("2 people still need a birthday").
- Drawn as inline SVG in the app, with no images from the internet.

## Tech Lead notes
- Data already exists: people with and without `birth_month`. No schema change.
- SVG with CSS animation; a few KB. Leaf positions come from a fixed layout of, say, 60 slots, filled in order, so the tree looks the same each visit.
- With more people than slots, the tree grows extra branches, or leaves stand for groups. Decide when we see real family sizes.

## Questions for the Product Owner
1. Does "complete" also mean anniversaries are filled in, or only birthdays?
2. In build 2, should faces found in photos but not yet named count as missing leaves?
3. Should the full tree also appear on the monitor as a one-time celebration when the family is complete?
