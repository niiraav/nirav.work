---
title: "NEEDS HUMAN REVIEW — {{niche}} Stage {{stage}}"
date: {{date}}
niche: "{{niche}}"
stage: {{stage}}
reason: "{{reason}}"
tags:
  - startup
  - escalated
---

# NEEDS HUMAN REVIEW — {{niche}}

**Stage {{stage}} escalated on {{date}}**
**Reason**: {{reason}}

---

## Disputed / Unresolved Points

{{disputed_points}}

## What Would Resolve This

{{resolution_guidance}}

---

## Resume Command

Once you've resolved the disputed points, add your notes to the session JSON
and resume:
```
python main.py --resume {{session_id}} --stage {{stage}}
```

**Session file**: `idea-validator/sessions/{{session_id}}.json`
