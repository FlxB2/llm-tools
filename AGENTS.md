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

### deviceDemo

- Run it before capturing screenshots for anything people will see (store listings, landing pages,
  docs), so the status bar shows 9:41 and a full battery instead of the real time and state.
- Use `--theme` and `--locale` to capture every theme and language variant from one device instead
  of asking the user to change settings. Prefer `--app` for the language: it's faster and doesn't
  restart anything.
- Run `--reset` afterwards, and set the theme and language back to what they were; it may be an
  emulator the user or another session keeps using.
- Drive the app itself with the UI automation tool you already have (e.g. Maestro); this only
  covers device settings.

### compareImages

- Reach for it whenever the user should choose between or check several images: design variants,
  before and after a change, screenshots in each language or theme. One labelled sheet is easier to
  judge than several files.
- Use `--diff` to check what a change actually did to a screenshot, and quote the changed share.
- Use `--zoom` when the difference is small (an icon, a border, a line of text).
- Look at the sheet yourself before showing it, and say what to look for.

## Adding a tool

- One folder per tool, named after it, with a `README.md` that says what it does, how to use it and
  what it does not do. Add a section for it here, and a row to the table in the root `README.md`.
- No dependencies and no build step, so it works as soon as it's copied.
- This repo is public. Nothing project-specific goes in: no names, paths, URLs, credentials or
  content from the projects a tool was first built for.
