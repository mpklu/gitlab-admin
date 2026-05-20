"""Tree -> single self-contained HTML report (Layout B).

The output is a complete HTML5 document with inline CSS, inline JS,
and a JSON data island. No external assets, no CDN.

Security: the JS never uses innerHTML / outerHTML. All DOM construction
goes through createElement + replaceChildren so untrusted strings
(project names, descriptions) can't be interpreted as HTML.
"""

from __future__ import annotations

from . import render_json
from .model import Tree

# CSS and JS land in Tasks 2 and 3. For now the template is the minimum
# that surfaces the data island and a stub body.

_HTML_HEAD = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>gitlab-admin — org browser</title>
<style>/* CSS lands in Task 2 */</style>
</head>
"""

_HTML_BODY_STUB = """\
<body>
<script type="application/json" id="org-data">{data_json}</script>
<script>/* JS lands in Task 3 */</script>
</body>
</html>
"""


def render(tree: Tree) -> str:
    """Return a complete self-contained HTML string."""
    data_json = render_json.render(tree).rstrip()
    return _HTML_HEAD + _HTML_BODY_STUB.format(data_json=data_json)
