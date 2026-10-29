# three.js

Vendored from the npm package `three` 0.186.1, unmodified, under the MIT license in `LICENSE`.
The files here are `build/three.module.js` and `build/three.core.js`, plus add-ons at their package paths: `examples/jsm/controls/OrbitControls.js`, `examples/jsm/environments/RoomEnvironment.js`, and the wide lines in `examples/jsm/lines/` (`LineSegments2.js`, `LineSegmentsGeometry.js` and `LineMaterial.js`).
bricky's headless renderer serves these files to Chromium itself, so renders never touch the network.
The standalone HTML viewer loads the same version from jsDelivr instead; `bricky.render.THREE_VERSION` names it in one place.

To update: `npm pack three@<version>`, copy these files and `LICENSE` here, and change `THREE_VERSION`.
