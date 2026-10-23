from exploreit.content import extract_content

URL = "https://example.com/"

PAGE = """
<html>
  <head>
    <title>  Example
      Domain </title>
    <meta name="Description" content="An example page.">
    <meta name="keywords" content="web, crawler , ,graphs">
    <style>body { color: red; }</style>
  </head>
  <body>
    <h1>Hello</h1>
    <script>console.log("hidden")</script>
    <p>Visible   text.</p>
    <meta itemprop="keywords" content="crawler,python">
  </body>
</html>
"""


def test_extracts_title_meta_tags_and_body() -> None:
    content = extract_content(PAGE, URL)

    assert content.url == URL
    assert content.title == "Example Domain"
    assert content.description == "An example page."
    assert content.keywords == ["web", "crawler", "graphs", "python"]
    assert content.body == "Hello Visible text."


def test_open_graph_description_is_used_as_fallback() -> None:
    html = '<meta property="og:description" content="From Open Graph.">'

    assert extract_content(html, URL).description == "From Open Graph."


def test_page_without_metadata() -> None:
    content = extract_content("<p>Only text</p>", URL)

    assert content.title == ""
    assert content.description == ""
    assert content.keywords == []
    assert content.body == "Only text"
