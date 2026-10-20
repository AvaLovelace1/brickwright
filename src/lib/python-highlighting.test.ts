import { expect, test } from "vitest";
import { highlightPython } from "./python-highlighting";

test.each([
  "",
  'def build():\n    return Element("3001", Color.RED)\n',
  '# A comment\r\nvalue = "<script>alert(1)</script>"\r\n',
  'text = """a multiline\nstring with # and 42\n"""\n',
  "b.connect(p1,\n  p1.find_connector(…),\n  p2.find_connector(…))",
])("preserves Python source exactly: %s", (code) => {
  expect(
    highlightPython(code)
      .map((token) => token.content)
      .join(""),
  ).toBe(code);
});

test("distinguishes Python syntax, including comments inside strings", () => {
  const tokens = highlightPython(
    'def build():\n    value = "# not a comment"\n    return 20  # parts\n',
  );
  const find = (content: string) => tokens.find((token) => token.content === content);
  expect(find("def")?.kind).toBe("keyword");
  expect(find("build")?.kind).toBe("function");
  expect(find("20")?.kind).toBe("constant");
  expect(
    tokens
      .filter((token) => token.kind === "string")
      .map((token) => token.content)
      .join(""),
  ).toBe('"# not a comment"');
  expect(
    tokens
      .filter((token) => token.kind === "comment")
      .map((token) => token.content)
      .join(""),
  ).toBe("# parts");
});
