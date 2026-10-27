# three.js

Vendored from the npm package `three` 0.186.1 (`build/three.module.js` and `build/three.core.js`),
unmodified, under the MIT licence in `LICENSE`. bricky's headless renderer serves these files to
Chromium itself, so renders never touch the network. The standalone HTML viewer loads the same
version from jsDelivr instead; `bricky.render.THREE_VERSION` names it in one place.

To update: `npm pack three@<version>`, copy the two files and `LICENSE` here, and change
`THREE_VERSION`.
