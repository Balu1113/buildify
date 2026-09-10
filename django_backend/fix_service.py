#!/usr/bin/env python
# Script to fix the f-string format specifier error in service.py

with open(r'c:\Users\balaji.talati\Desktop\agentic-ai-course\ai-student-project-manager\django_backend\pipeline\service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# The issue is that /tasks.models is being interpreted as a format specifier
# We need to escape it by using \/ to escape the forward slash
# Line 732 (index 731) contains the problematic text
lines[731] = "IMPORTANT: You MUST import from the actual source modules. If a file is at tasks\\/models.py, import from tasks\\.models. Do NOT invent functions or classes that don't exist.\n"

with open(r'c:\Users\balaji.talati\Desktop\agentic-ai-course\ai-student-project-manager\django_backend\pipeline\service.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("File updated successfully")
