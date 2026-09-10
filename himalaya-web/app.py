#!/usr/bin/env python3
"""
Himalaya Web-UI
Schlankes Webmail-Interface für Himalaya CLI
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
import subprocess
import os
import shlex

app = Flask(__name__)

# Himalaya CLI Konfiguration
HIMALAYA_CMD = "himalaya"
HIMALAYA_CONFIG = os.path.expanduser("~/.config/himalaya/config.toml")

def run_himalaya(args):
    """Führt Himalaya CLI Befehl aus und gibt Output zurück"""
    try:
        # v2.x Syntax: himalaya [OPTIONS] <COMMAND>
        # Beispiel: himalaya envelope list --limit 50
        cmd = [HIMALAYA_CMD] + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return {"success": False, "error": result.stderr}
        return {"success": True, "output": result.stdout}
    except Exception as e:
        return {"success": False, "error": str(e)}

def parse_email_list(output):
    """Parsed Himalaya v2.x envelope list Output (Tabelle)"""
    emails = []
    lines = output.strip().split("\n")
    
    # v2.x Output ist eine Tabelle:
    # ┌────┬──────┬─────────┬─────────┬────────────┐
    # │ ID │ FLAGS│ FROM    │ SUBJECT │ DATE       │
    # ├────┼──────┼─────────┼─────────┼────────────┤
    # │1234│ N    │ peter@..│ Betreff │ 2025-01-15 │
    
    for line in lines:
        # Nur Zeilen mit │ sind Daten-Zeilen
        if '│' in line and '──' not in line and 'ID' not in line:
            # Extrahiere Spalten zwischen │
            parts = [p.strip() for p in line.split('│') if p.strip()]
            if len(parts) >= 5:
                emails.append({
                    "id": parts[0].strip(),
                    "flags": parts[1].strip(),
                    "from": parts[2].strip(),
                    "subject": parts[3].strip(),
                    "date": parts[4].strip()
                })
    
    return emails

def parse_email_content(output):
    """Parsed Himalaya email content"""
    # Einfache Aufteilung nach Headern
    lines = output.strip().split("\n")
    headers = {}
    body = []
    in_body = False
    
    for line in lines:
        if in_body:
            body.append(line)
        elif line.strip() == "":
            in_body = True
        elif ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()
    
    return {
        "headers": headers,
        "body": "\n".join(body)
    }

@app.route("/")
def index():
    """Startseite - zeigt Inbox"""
    return redirect(url_for("inbox"))

@app.route("/inbox")
def inbox():
    """Zeigt Inbox Emails"""
    # v2.x: himalaya envelope list --page-size 50
    result = run_himalaya(["envelope", "list", "--page-size", "50"])
    if result["success"]:
        emails = parse_email_list(result["output"])
        return render_template("inbox.html", emails=emails, folder="INBOX")
    else:
        return render_template("error.html", error=result.get("error", "Unbekannter Fehler"))

@app.route("/folder/<folder_name>")
def folder(folder_name):
    """Zeigt Emails aus beliebigem Ordner"""
    # v2.x: himalaya envelope list --mailbox <name> --page-size 50
    result = run_himalaya(["envelope", "list", "--mailbox", folder_name, "--page-size", "50"])
    if result["success"]:
        emails = parse_email_list(result["output"])
        return render_template("inbox.html", emails=emails, folder=folder_name)
    else:
        return render_template("error.html", error=result.get("error", "Unbekannter Fehler"))

@app.route("/email/<email_id>")
def read_email(email_id):
    """Zeigt Email Inhalt"""
    # v2.x: himalaya message show <id>
    result = run_himalaya(["message", "show", email_id])
    if result["success"]:
        email_data = parse_email_content(result["output"])
        return render_template("email.html", email=email_data, email_id=email_id)
    else:
        return render_template("error.html", error=result.get("error", "Unbekannter Fehler"))

@app.route("/compose")
def compose():
    """Zeigt compose Formular"""
    return render_template("compose.html")

@app.route("/send", methods=["POST"])
def send_email():
    """Sendet Email"""
    to = request.form.get("to", "")
    subject = request.form.get("subject", "")
    body = request.form.get("body", "")
    
    # v2.x: himalaya message send --to <email> --subject <subject>
    # Body als stdin
    try:
        import tempfile
        # Temporäre Datei für den Body
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write(body)
            temp_file = f.name
        
        # himalaya message send < to_file
        cmd = f'{HIMALAYA_CMD} message send --to {shlex.quote(to)} --subject {shlex.quote(subject)} < {shlex.quote(temp_file)}'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        os.unlink(temp_file)
        
        if result.returncode != 0:
            return render_template("error.html", error=result.stderr)
        return redirect(url_for("inbox"))
    except Exception as e:
        if 'temp_file' in locals():
            os.unlink(temp_file)
        return render_template("error.html", error=str(e))

@app.route("/folders")
def folders():
    """Zeigt alle Ordner"""
    # v2.x: himalaya mailbox list
    result = run_himalaya(["mailbox", "list"])
    if result["success"]:
        folders_list = [f.strip() for f in result["output"].strip().split("\n") if f.strip()]
        return render_template("folders.html", folders=folders_list)
    else:
        return render_template("error.html", error=result.get("error", "Unbekannter Fehler"))

@app.route("/api/health")
def health():
    """Health check endpoint"""
    result = run_himalaya(["--version"])
    return jsonify({
        "status": "ok" if result["success"] else "error",
        "himalaya": result.get("output", "unknown").strip() if result["success"] else result.get("error", "unknown")
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8055, debug=False)
