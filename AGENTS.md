# AGENTS.md

Guidance for AI agents using or extending this repo. Read the tool's own `README.md` for what it
does; this file says when and how to reach for it.

## Using a tool

Copy the tool's folder (or the one file you need) into the project you are working on. Tools have
no dependencies and no build step, so nothing needs installing.

### editHTML

- **Design variants:** when asked for several versions of something on a web page, mark them up as
  one `data-variants` group (one child per option, each with a `data-variant` label) instead of
  stacking labelled copies, and load `text-editor.js` on the page, in development only. The user
  then steps through them in place with **Options**.
- **Copy edits:** the user can rewrite text in place with **Edit text**, but edits stay in their
  browser and never reach the source files. Ask them to copy **Changes** and apply the list
  yourself.
- **Spacing:** the user can tune margin, padding and gap on the live page with **Spacing**. The
  copied **Changes** list each element by tag and classes with old → new px values; find that
  element in the source and translate the values into the project's own spacing scale (e.g. its
  Tailwind steps or design tokens) rather than pasting raw px.
- Remove the variants you didn't pick, and the script, once the user has decided.

### phoneFrame

- Reach for it whenever app screenshots (simulator, emulator, Maestro or other UI test runs) need to
  look like a phone: landing pages, store listings, decks, READMEs.
- Run it in place with `uv`; don't copy it into the project unless the project should regenerate
  the images itself (then commit the script next to the assets it makes).
- Leave `--platform` and `--cutout` on auto unless the screenshot was resized or cropped, since the
  guess relies on the exact device resolution.
- If the project has a designer-made device frame (a Figma export), pass it with `--mockup` so the
  images match the rest of the design.
- Look at one result before framing a whole batch.

## Adding a tool

- One folder per tool, named after it, with a `README.md` that says what it does, how to use it and
  what it does not do. Add a section for it here, and a row to the table in the root `README.md`.
- No dependencies and no build step, so it works as soon as it's copied.
- This repo is public. Nothing project-specific goes in: no names, paths, URLs, credentials or
  content from the projects a tool was first built for.
