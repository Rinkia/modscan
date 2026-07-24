# Extension points in `markdown 3.10.2`

12 candidate(s), ranked by moddability. No LLM was used — this is the static ranking only.

**18 candidates score exactly 1.00, and this list shows 12 of them.** The 6 left out are not ranked lower — ties are broken by module name, so the cut through this band is alphabetical, not evidence-based. Widen `--limit` to see the whole band.

| # | Extension point | Category | Score | Why |
|---|---|---|---|---|
| 1 | `markdown.extensions.abbr:AbbrExtension` | subclass | 1.00 | [MS-MOD-PUBLIC] public class; [MS-MOD-CLASSROLE] name ends in 'Extension' — role type; [MS-MOD-BASEROLE] subclasses a 'Extension' role type |
| 2 | `markdown.extensions.admonition:AdmonitionExtension` | subclass | 1.00 | [MS-MOD-PUBLIC] public class; [MS-MOD-CLASSROLE] name ends in 'Extension' — role type; [MS-MOD-BASEROLE] subclasses a 'Extension' role type |
| 3 | `markdown.extensions.attr_list:AttrListExtension` | subclass | 1.00 | [MS-MOD-PUBLIC] public class; [MS-MOD-CLASSROLE] name ends in 'Extension' — role type; [MS-MOD-BASEROLE] subclasses a 'Extension' role type |
| 4 | `markdown.extensions.codehilite:CodeHiliteExtension` | subclass | 1.00 | [MS-MOD-PUBLIC] public class; [MS-MOD-CLASSROLE] name ends in 'Extension' — role type; [MS-MOD-BASEROLE] subclasses a 'Extension' role type |
| 5 | `markdown.extensions.def_list:DefListExtension` | subclass | 1.00 | [MS-MOD-PUBLIC] public class; [MS-MOD-CLASSROLE] name ends in 'Extension' — role type; [MS-MOD-BASEROLE] subclasses a 'Extension' role type |
| 6 | `markdown.extensions.extra:ExtraExtension` | subclass | 1.00 | [MS-MOD-PUBLIC] public class; [MS-MOD-CLASSROLE] name ends in 'Extension' — role type; [MS-MOD-BASEROLE] subclasses a 'Extension' role type |
| 7 | `markdown.extensions.fenced_code:FencedCodeExtension` | subclass | 1.00 | [MS-MOD-PUBLIC] public class; [MS-MOD-CLASSROLE] name ends in 'Extension' — role type; [MS-MOD-BASEROLE] subclasses a 'Extension' role type |
| 8 | `markdown.extensions.footnotes:FootnoteExtension` | subclass | 1.00 | [MS-MOD-PUBLIC] public class; [MS-MOD-CLASSROLE] name ends in 'Extension' — role type; [MS-MOD-BASEROLE] subclasses a 'Extension' role type |
| 9 | `markdown.extensions.legacy_attrs:LegacyAttrExtension` | subclass | 1.00 | [MS-MOD-PUBLIC] public class; [MS-MOD-CLASSROLE] name ends in 'Extension' — role type; [MS-MOD-BASEROLE] subclasses a 'Extension' role type |
| 10 | `markdown.extensions.legacy_em:LegacyEmExtension` | subclass | 1.00 | [MS-MOD-PUBLIC] public class; [MS-MOD-CLASSROLE] name ends in 'Extension' — role type; [MS-MOD-BASEROLE] subclasses a 'Extension' role type |
| 11 | `markdown.extensions.md_in_html:MarkdownInHtmlExtension` | subclass | 1.00 | [MS-MOD-PUBLIC] public class; [MS-MOD-CLASSROLE] name ends in 'Extension' — role type; [MS-MOD-BASEROLE] subclasses a 'Extension' role type |
| 12 | `markdown.extensions.meta:MetaExtension` | subclass | 1.00 | [MS-MOD-PUBLIC] public class; [MS-MOD-CLASSROLE] name ends in 'Extension' — role type; [MS-MOD-BASEROLE] subclasses a 'Extension' role type |

## Plugin registration points

How this package discovers plugins — register against these rather than subclassing them.

| Mechanism | Location | Call sites |
|---|---|---|
| `import_module` | `markdown.core` | 1 |
| `find_spec` | `markdown.htmlparser` | 1 |
| `entry_points` | `markdown.util` | 1 |
