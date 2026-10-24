import { createHighlighterCoreSync } from "@shikijs/core";
import { createJavaScriptRegexEngine } from "@shikijs/engine-javascript";
import python from "@shikijs/langs/python";

// Shiki reports each token's theme color, so every kind gets a distinct placeholder color to read back.
const colors = {
  plain: "#000000",
  keyword: "#000001",
  string: "#000002",
  constant: "#000003",
  comment: "#000004",
  function: "#000005",
} as const;

export type PythonTokenKind = keyof typeof colors;
export interface PythonToken {
  content: string;
  kind: PythonTokenKind;
}

const kinds = new Map<string, PythonTokenKind>(
  Object.entries(colors).map(([kind, color]) => [color, kind as PythonTokenKind]),
);

const highlighter = createHighlighterCoreSync({
  langs: [python],
  engine: createJavaScriptRegexEngine(),
  themes: [
    {
      name: "brickbrand-python",
      type: "light",
      colors: { "editor.foreground": colors.plain },
      tokenColors: [
        {
          scope: ["keyword", "storage.type", "storage.modifier"],
          settings: { foreground: colors.keyword },
        },
        {
          scope: [
            "entity.name.function",
            "support.function",
            "meta.function-call.generic",
            "support.type",
            "support.class",
          ],
          settings: { foreground: colors.function },
        },
        { scope: ["punctuation"], settings: { foreground: colors.plain } },
        {
          scope: ["string", "punctuation.definition.string"],
          settings: { foreground: colors.string },
        },
        {
          scope: ["constant.numeric", "constant.language", "constant.character"],
          settings: { foreground: colors.constant },
        },
        {
          scope: ["comment", "punctuation.definition.comment"],
          settings: { foreground: colors.comment },
        },
      ],
    },
  ],
});

/** Tokenize source without changing its text or interpreting it as HTML. */
export function highlightPython(code: string): PythonToken[] {
  const newlines = code.match(/\r\n|\r|\n/g) ?? [];
  const { tokens } = highlighter.codeToTokens(code.replace(/\r\n|\r/g, "\n"), {
    lang: "python",
    theme: "brickbrand-python",
  });
  return tokens.flatMap((line, index) => {
    const result = line.map((token): PythonToken => {
      const kind = kinds.get(token.color ?? "") ?? "plain";
      return { content: token.content, kind };
    });
    if (newlines[index]) result.push({ content: newlines[index], kind: "plain" });
    return result;
  });
}
