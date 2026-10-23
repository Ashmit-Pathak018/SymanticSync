from pathlib import Path

p = Path("README.md")
content = p.read_text(encoding="utf-8")

old_line = "| **Presentation Cheatsheet** | 1-page quick reference (pitch, 5 contributions, 10 faculty Q&As, commands) | [`docs/PRESENTATION_CHEATSHEET.md`](docs/PRESENTATION_CHEATSHEET.md) |"
new_line = "| **Explanation Package** | Complete defense & technical explanation suite folder | [`explanation/`](explanation/README.md) |\n| **Presentation Cheatsheet** | 1-page quick reference (pitch, 5 contributions, 10 faculty Q&As, commands) | [`docs/PRESENTATION_CHEATSHEET.md`](docs/PRESENTATION_CHEATSHEET.md) |"

if old_line in content:
    content = content.replace(old_line, new_line, 1)
    p.write_text(content, encoding="utf-8")
    print("README.md updated with explanation folder link!")
else:
    print("Old line not found directly, checking with CRLF...")
    old_line_crlf = old_line.replace("\n", "\r\n")
    new_line_crlf = new_line.replace("\n", "\r\n")
    if old_line_crlf in content:
        content = content.replace(old_line_crlf, new_line_crlf, 1)
        p.write_text(content, encoding="utf-8")
        print("README.md updated with explanation folder link (CRLF)!")
    else:
        print("Could not find line directly.")
