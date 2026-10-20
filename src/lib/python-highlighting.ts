import { createHighlighterCoreSync } from "@shikijs/core";
import { createJavaScriptRegexEngine } from "@shikijs/engine-javascript";
import python from "@shikijs/langs/python";

const syntax = {
  plain: { color: "#1B2A34", className: "text-text" },
  keyword: { color: "#A65301", className: "font-semibold text-(--python-keyword)" },
  string: { color: "#206873", className: "text-(--python-string)" },
  constant: { color: "#873461", className: "text-(--python-constant)" },
  comment: { color: "#2D5F2C", className: "italic text-(--python-comment)" },
  function: { color: "#003373", className: "text-(--python-function)" },
} as const;

export type PythonTokenKind = keyof typeof syntax;
export interface PythonToken {
  content: string;
  kind: PythonTokenKind;
  className: string;
}

const kinds = new Map<string, PythonTokenKind>(
  Object.entries(syntax).map(([kind, style]) => [style.color, kind as PythonTokenKind]),
);

const highlighter = createHighlighterCoreSync({
  langs: [python],
  engine: createJavaScriptRegexEngine(),
  themes: [
    {
      name: "brickbrand-python",
      type: "light",
      colors: { "editor.foreground": syntax.plain.color, "editor.background": "#F9F7F1" },
      tokenColors: [
        {
          scope: ["keyword", "storage.type", "storage.modifier"],
          settings: { foreground: syntax.keyword.color },
        },
        {
          scope: [
            "entity.name.function",
            "support.function",
            "meta.function-call.generic",
            "support.type",
            "support.class",
          ],
          settings: { foreground: syntax.function.color },
        },
        { scope: ["punctuation"], settings: { foreground: syntax.plain.color } },
        {
          scope: ["string", "punctuation.definition.string"],
          settings: { foreground: syntax.string.color },
        },
        {
          scope: ["constant.numeric", "constant.language", "constant.character"],
          settings: { foreground: syntax.constant.color },
        },
        {
          scope: ["comment", "punctuation.definition.comment"],
          settings: { foreground: syntax.comment.color },
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
      const kind = kinds.get(token.color?.toUpperCase() ?? "") ?? "plain";
      return { content: token.content, kind, className: syntax[kind].className };
    });
    if (newlines[index])
      result.push({ content: newlines[index], kind: "plain", className: syntax.plain.className });
    return result;
  });
}
