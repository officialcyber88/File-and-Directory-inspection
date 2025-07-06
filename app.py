import sys
import tempfile
import json
import csv
import traceback
import subprocess
import os
import zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import textwrap

# Auto-install PyYAML if needed
try:
    import yaml
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml"])
    import yaml

# Ensure Gradio is present
try:
    import gradio as gr
except ImportError:
    print("Please install gradio: pip install gradio", file=sys.stderr)
    sys.exit(1)

# No exclusions—accept all files
_EXCLUDE_EXTS = set()

# Syntax highlighting mapping for Markdown
_SYNTAX_MAP = {
    '.py': 'python', '.js': 'javascript', '.mjs': 'javascript',
    '.html': 'html', '.css': 'css', '.json': 'json',
    '.yml': 'yaml', '.yaml': 'yaml', '.md': 'markdown',
    '.sh': 'bash', '.java': 'java', '.c': 'c', '.cpp': 'cpp',
    '.h': 'cpp', '.cs': 'csharp', '.php': 'php', '.rb': 'ruby',
    '.go': 'go', '.rs': 'rust', '.swift': 'swift', '.kt': 'kotlin',
    '.ts': 'typescript', '.sql': 'sql', '.xml': 'xml',
    '.svg': 'xml', '.ini': 'ini', '.cfg': 'ini',
    '.toml': 'toml', '.lock': 'json',
}

def human_readable_size(num, suffix='B'):
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Y{suffix}"

def is_text_file(path: Path, blocksize: int = 1024) -> bool:
    try:
        with path.open('rb') as f:
            if b'\0' in f.read(blocksize):
                return False
        return True
    except Exception:
        return False

def build_tree(root: Path):
    tree = []
    try:
        root_name = root.name or "root_directory"
        tree.append({
            "path": ".",
            "is_dir": True,
            "name": root_name,
            "size": 0,
            "hr_size": human_readable_size(0),
            "modified": root.stat().st_mtime
        })
        for p in root.rglob('*'):
            if p == root:
                continue
            try:
                rel = p.relative_to(root)
                stat = p.stat()
                tree.append({
                    "path": str(rel),
                    "is_dir": p.is_dir(),
                    "name": p.name,
                    "size": stat.st_size,
                    "hr_size": human_readable_size(stat.st_size),
                    "modified": stat.st_mtime
                })
            except Exception as e:
                print(f"Skipping {p}: {e}")
    except Exception as e:
        print(f"Error building tree: {e}")
        traceback.print_exc()
    return tree

def build_files(root: Path, max_workers: int = None):
    max_workers = max_workers or (os.cpu_count() or 4)
    all_files = [p for p in root.rglob('*') if p.is_file()]

    def read_and_clean(p):
        if not is_text_file(p):
            return None
        try:
            text = p.read_text(encoding='utf-8', errors='replace')
            lines = []
            for line in text.splitlines():
                if len(line) > 120:
                    lines.extend(textwrap.wrap(line, width=120, break_long_words=False))
                else:
                    lines.append(line)
            return "\n".join(lines)
        except Exception as e:
            return f"Error reading {p}: {e}"

    files = []
    with ThreadPoolExecutor(max_workers=max_workers) as exe:
        futures = {exe.submit(read_and_clean, p): p for p in all_files}
        for fut in as_completed(futures):
            content = fut.result()
            if content is not None:
                p = futures[fut]
                files.append({
                    "path": str(p.relative_to(root)),
                    "content": content,
                    "syntax": _SYNTAX_MAP.get(p.suffix.lower(), '')
                })
    return files

def export_txt(tree, files):
    parts = []
    if tree:
        parts.append("Directory Structure:")
        for e in tree:
            indent = '    ' * e['path'].count(os.sep)
            parts.append(f"{indent}{e['name']} ({e['hr_size']}): {e['path']}")
    if files:
        parts.append("\nFile Contents:")
        for f in files:
            parts.append(f"\nFile: {f['path']}\n{f['content']}")
    return "\n".join(parts) or "No content found"

def export_json(tree, files):
    return json.dumps({
        "metadata": {
            "directory": {
                "name": tree[0]['name'] if tree else "",
                "file_count": len(files),
                "directory_count": sum(1 for t in tree if t['is_dir'])
            }
        },
        "structure": tree,
        "files": files
    }, indent=2)

def export_jsonl(tree, files):
    lines = []
    if tree:
        for entry in tree:
            lines.append(json.dumps({
                "type": "structure",
                "data": entry
            }))
    if files:
        for file_entry in files:
            lines.append(json.dumps({
                "type": "content",
                "data": file_entry
            }))
    return "\n".join(lines)

def export_yaml(tree, files):
    return yaml.dump({
        "metadata": {
            "directory": {
                "name": tree[0]['name'] if tree else "",
                "file_count": len(files),
                "directory_count": sum(1 for t in tree if t['is_dir'])
            }
        },
        "structure": tree,
        "files": files
    }, sort_keys=False, allow_unicode=True)

def export_markdown(tree, files):
    md = []
    if tree:
        md.append("# Directory Structure")
        for e in tree:
            indent = '  ' * e['path'].count(os.sep)
            md.append(f"{indent}- **{e['name']}** ({e['hr_size']}): `{e['path']}`")
    if files:
        md.append("\n# File Contents")
        for f in files:
            lang = f['syntax'] or 'text'
            md.append(f"\n## {f['path']}\n```{lang}\n{f['content']}\n```")
    return "\n".join(md) or "No content found"

def export_csv(tree, files):
    from io import StringIO
    out = StringIO()
    w = csv.writer(out)
    w.writerow(["Type","Path","Size","Modified"])
    for e in tree:
        w.writerow([
            "DIR" if e['is_dir'] else "FILE",
            e['path'], e['size'], e['modified']
        ])
    if files:
        w.writerow([])
        w.writerow(["File Path","Content Excerpt"])
        for f in files:
            excerpt = (f['content'][:200] + '...') if len(f['content'])>200 else f['content']
            w.writerow([f['path'], excerpt])
    return out.getvalue()

def export_tsv(tree, files):
    from io import StringIO
    out = StringIO()
    w = csv.writer(out, delimiter='\t')
    w.writerow(["Type","Path","Size","Modified"])
    for e in tree:
        w.writerow([
            "DIR" if e['is_dir'] else "FILE",
            e['path'], e['size'], e['modified']
        ])
    if files:
        w.writerow([])
        w.writerow(["File Path","Content Excerpt"])
        for f in files:
            excerpt = (f['content'][:200] + '...') if len(f['content'])>200 else f['content']
            w.writerow([f['path'], excerpt])
    return out.getvalue()

def export_html(tree, files):
    lines = ['<html><head><meta charset="utf-8"><title>File Inspector Report</title></head><body>']
    lines.append(f"<h1>Directory: {tree[0]['name'] if tree else ''}</h1>")
    if tree:
        lines.append("<details open><summary>Structure</summary><pre>")
        for e in tree:
            lines.append(f"{e['path']} ({e['hr_size']})")
        lines.append("</pre></details>")
    if files:
        lines.append("<details><summary>File Contents</summary>")
        for f in files:
            lines.append(f"<h2>{f['path']}</h2><pre>{f['content']}</pre>")
        lines.append("</details>")
    lines.append("</body></html>")
    return "\n".join(lines)

_FORMATS = {
    "TXT":      {"ext":"txt",  "exporter":export_txt,      "desc":"Plain text. Quick & simple."},
    "JSON":     {"ext":"json", "exporter":export_json,     "desc":"Structured JSON for APIs."},
    "JSONL":    {"ext":"jsonl","exporter":export_jsonl,    "desc":"JSON Lines for streaming/NDJSON."},
    "YAML":     {"ext":"yaml", "exporter":export_yaml,     "desc":"Human-friendly YAML."},
    "Markdown": {"ext":"md",   "exporter":export_markdown, "desc":"Markdown with syntax coloring."},
    "CSV":      {"ext":"csv",  "exporter":export_csv,      "desc":"CSV for spreadsheets."},
    "TSV":      {"ext":"tsv",  "exporter":export_tsv,      "desc":"TSV for tab-delimited data."},
    "HTML":     {"ext":"html","exporter":export_html,      "desc":"Interactive HTML report."}
}

def process_and_save(source: str, local_path: str, zip_file, action: str, fmt: str):
    try:
        if source == "Upload ZIP":
            if zip_file is None:
                return None, "Error: no ZIP uploaded"
            tmpdir = Path(tempfile.mkdtemp())
            with zipfile.ZipFile(zip_file.name, 'r') as z:
                z.extractall(tmpdir)
            root = tmpdir
        else:
            root = Path(local_path).expanduser().resolve()

        if not root.is_dir():
            return None, "Error: Invalid directory"

        tree  = build_tree(root)  if "Tree" in action else []
        files = build_files(root) if "Extract Code" in action else []

        if fmt not in _FORMATS:
            return None, f"Error: Unknown format {fmt}"
        exporter = _FORMATS[fmt]["exporter"]
        content  = exporter(tree, files)

        out_name = f"{root.name or 'output'}.{_FORMATS[fmt]['ext']}"
        out_path = Path(tempfile.gettempdir()) / out_name
        out_path.write_text(content, encoding='utf-8')
        return str(out_path), content

    except Exception as e:
        return None, f"Processing error: {e}\n{traceback.format_exc()}"

def explain_format(fmt: str):
    info = _FORMATS.get(fmt)
    return f"**{fmt} Format**\n{info['desc']}" if info else "Select a valid format"

def launch_app():
    with gr.Blocks(theme=gr.themes.Soft(), title="File Inspector") as demo:
        gr.Markdown("# File Inspector Tool")
        gr.Markdown("Choose a local folder or upload a ZIP archive, then view/export its contents.")

        with gr.Row():
            with gr.Column(scale=2):
                source_input = gr.Dropdown(
                    label="Input Source",
                    choices=["Local Path", "Upload ZIP"],
                    value="Local Path"
                )
                dir_input = gr.Textbox(
                    label="Directory Path",
                    placeholder="/path/to/project",
                    value=str(Path.home())
                )
                zip_input = gr.File(
                    label="Upload ZIP Archive",
                    file_types=[".zip"],
                    visible=False
                )
                action_input = gr.Dropdown(
                    label="Action",
                    choices=["Display Tree", "Extract Code", "Display Tree + Extract Code"],
                    value="Display Tree + Extract Code"
                )
                format_input = gr.Dropdown(
                    label="Export Format",
                    choices=list(_FORMATS.keys()),
                    value="TXT"
                )
                fmt_explain = gr.Markdown(explain_format("TXT"))
                run_btn = gr.Button("Run", variant="primary")
                download = gr.File(label="Download Output", interactive=False)

            with gr.Column(scale=3):
                content_box = gr.TextArea(
                    label="Output",
                    lines=20,
                    interactive=False,
                    elem_id="output_txt",
                    elem_classes=["output-box"],
                    show_copy_button=True  # <-- use built-in copy
                )

        source_input.change(
            fn=lambda src: (
                gr.update(visible=(src=="Local Path")),
                gr.update(visible=(src=="Upload ZIP"))
            ),
            inputs=source_input,
            outputs=[dir_input, zip_input]
        )

        format_input.change(
            fn=explain_format,
            inputs=format_input,
            outputs=fmt_explain
        )

        run_btn.click(
            fn=process_and_save,
            inputs=[source_input, dir_input, zip_input, action_input, format_input],
            outputs=[download, content_box]
        )

        demo.css = """
        .output-box textarea {
            font-family: 'Courier New', monospace !important;
            white-space: pre !important;
            user-select: text !important;
            -webkit-user-select: text !important;
        }
        """
        demo.launch()

if __name__ == "__main__":
    launch_app()
