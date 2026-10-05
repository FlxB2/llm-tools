# editHTML

A floating bar for any web page, in plain JavaScript with no build step. Nothing it does reaches the
page's source: edits live in the browser (`localStorage`, per page) until you copy them out.

- **Edit text:** turn on edit mode, click any text and type. Enter keeps the edit, Escape undoes
  it. Edits are kept in the browser per page and come back the next time the editor runs there.
  **Changes** lists every edit as old → new, ready to copy back into a prompt.
- **Options:** switch between design variants that the page marks up, one at a time:

  ```html
  <div data-variants="Button">
    <div data-variant="Solid">…</div>
    <div data-variant="Outline">…</div>
  </div>
  ```

  The pick is remembered per page.
- **Spacing:** click any element to change its margin, padding and gap in px. The margin (orange)
  and padding (green) are drawn over the page like the browser's inspector. Drag a field left or right to scrub its value like in Figma, or
  use − + and ↑ ↓; Shift steps by 8, and **↑ Parent** moves to the enclosing element. Changes are inline styles, listed
  under **Changes** with the element's tag and classes.

## Use it

- **In a page:** `<script src="text-editor.js"></script>`.
- **On any site:** open `index.html` and drag its button to the bookmarks bar. Sites with a strict
  Content Security Policy may block bookmarklets.
