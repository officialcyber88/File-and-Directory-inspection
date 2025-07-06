---
title: File And Directory Inspection
emoji: 🔥
colorFrom: yellow
colorTo: red
sdk: gradio
sdk_version: 5.35.0
app_file: app.py
pinned: false
license: unlicense
---

# File Inspector Tool

The File Inspector is a Gradio-based web application for analyzing the contents of a local directory or ZIP archive. It can display the full folder structure, extract readable text and code files, and export the results in multiple formats.

## Features

- Supports both local directories and uploaded ZIP archives
- Displays full directory tree with size and timestamp information
- Extracts readable text/code content from supported files
- Supports syntax highlighting for common programming languages
- Allows export to multiple formats:
  - TXT (plain text)
  - JSON / JSONL
  - YAML
  - Markdown
  - CSV / TSV
  - HTML

## How to Use

1. Choose the input source:
   - Local Path: enter a directory path
   - Upload ZIP: upload a `.zip` file
2. Select the desired action:
   - Display Tree
   - Extract Code
   - Display Tree + Extract Code
3. Choose an export format
4. Click "Run" to process the files
5. View the output and download the result

## Installation (Local Use)

To run this tool locally, install the required dependencies and start the app:

```bash
pip install gradio pyyaml
python app.py

Check out the configuration reference at https://huggingface.co/docs/hub/spaces-config-reference
