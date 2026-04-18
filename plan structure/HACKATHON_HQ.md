# 🏆 DevClash 2026 — Hackathon Command Center

> **Status**: ⏳ WAITING FOR PROBLEM STATEMENT  
> **Start**: April 18, 10:00 AM | **End**: April 19, 10:00 AM  
> **Track**: _TBD after problem reveal_  
> **Team Size**: 5 Members

---

## 📌 Table of Contents
1. [Problem Statement](#-1-problem-statement)
2. [Requirement Extraction Checklist](#-2-requirement-extraction-checklist)
3. [System Architecture](#-3-system-architecture)
4. [Tech Stack Decision](#-4-tech-stack-decision)
5. [Feature Ownership & Progress Tracker](#-5-feature-ownership--progress-tracker)
6. [Judging Rounds — Preparation Guide](#-6-judging-rounds--preparation-guide)
7. [Judge Q&A Preparation](#-7-judge-qa-preparation)
8. [Hourly Progress Log](#-8-hourly-progress-log)
9. [Bug Tracker](#-9-bug-tracker)
10. [AI Tools Disclosure Log](#-10-ai-tools-disclosure-log)
11. [Submission Checklist](#-11-submission-checklist)

---

## 📝 1. Problem Statement

### Raw Problem Statement
> _Paste the exact problem statement here once revealed at 10:00 AM_
>
> ...

### Our Interpretation (Plain English)
> _Rewrite the problem in your own words. What exactly are we building? What problem are we solving? For whom?_
>
> **What we are building**: ...  
> **Who is the user**: ...  
> **What pain point does it solve**: ...  
> **What does "done" look like**: ...

### Key Constraints / Rules from the Problem
> _List any specific constraints mentioned in the problem statement_
- [ ] Constraint 1: ...
- [ ] Constraint 2: ...
- [ ] Constraint 3: ...

### Scope Boundaries — What We ARE and ARE NOT Building
| ✅ In Scope | ❌ Out of Scope |
|------------|----------------|
| ... | ... |
| ... | ... |
| ... | ... |

---

## ✅ 2. Requirement Extraction Checklist

> **READ THE PROBLEM STATEMENT 3 TIMES.** Underline every verb (action = feature), every noun (entity = data model), every adjective (quality = validation rule).

### Functional Requirements (MUST have — this is 80% of scoring)
| # | Requirement (exact from problem statement) | Priority | Owner | Status |
|---|-------------------------------------------|----------|-------|--------|
| F1 | ... | 🔴 P0 | | ⬜ |
| F2 | ... | 🔴 P0 | | ⬜ |
| F3 | ... | 🟡 P1 | | ⬜ |
| F4 | ... | 🟡 P1 | | ⬜ |
| F5 | ... | 🟢 P2 | | ⬜ |
| F6 | ... | 🟢 P2 | | ⬜ |

> **Priority Guide**: P0 = Core (demo breaks without it), P1 = Important (judges will look for it), P2 = Nice-to-have (completeness points)

### Non-Functional Requirements
| # | Requirement | Notes |
|---|------------|-------|
| NF1 | App must run without manual intervention | Judges run it themselves |
| NF2 | Handle edge cases (empty/invalid/large inputs) | 80% scoring is on correctness |
| NF3 | Deterministic output (same input → same output) | No randomness in core logic |
| NF4 | Setup must be documented step-by-step | Judges follow your README |

### Edge Cases to Handle
| Input Scenario | Expected Behavior | Implemented? |
|---------------|-------------------|-------------|
| Empty input | Show validation error | ⬜ |
| Invalid format | Show clear error message | ⬜ |
| Very large input | Handle gracefully (truncate/paginate) | ⬜ |
| Special characters | Sanitize properly | ⬜ |
| Duplicate data | Handle or deduplicate | ⬜ |
| Network failure (if applicable) | Show fallback / retry | ⬜ |

---

## 🏗️ 3. System Architecture

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SYSTEM ARCHITECTURE                          │
│                    (Update after problem reveal)                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐       │
│   │              │     │              │     │              │       │
│   │   FRONTEND   │────▶│   BACKEND    │────▶│  DATABASE /  │       │
│   │   (Client)   │◀────│   (Server)   │◀────│   STORAGE    │       │
│   │              │     │              │     │              │       │
│   └──────────────┘     └──────────────┘     └──────────────┘       │
│         M3                  M2 + M1              M4                 │
│                                                                     │
│   ┌──────────────┐     ┌──────────────┐                             │
│   │  EXTERNAL    │     │   DEPLOY /   │                             │
│   │  APIs /      │     │   CI / CD    │                             │
│   │  SERVICES    │     │              │                             │
│   └──────────────┘     └──────────────┘                             │
│         M4                   M5                                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow Diagram
```
USER INPUT                    PROCESSING                     OUTPUT
─────────                    ──────────                     ──────
                                                           
[User Action] ──▶ [Frontend Validation] ──▶ [API Call]     
                                               │            
                                               ▼            
                                        [Backend Logic]     
                                               │            
                                               ▼            
                                        [Data Storage]      
                                               │            
                                               ▼            
                                        [Response]  ──▶ [Display Result]
```

### Component Breakdown
| Component | Responsibility | Owner | Tech Used |
|-----------|---------------|-------|-----------|
| Frontend UI | User interface, forms, display | M3 (Pixel) | ... |
| Backend API | Business logic, data processing | M2 (Engine) | ... |
| API Layer | Routes, middleware, validation | M4 (Bridge) | ... |
| Database/Storage | Data persistence | M4 (Bridge) | ... |
| External Services | Third-party APIs, if any | M4 (Bridge) | ... |
| DevOps | Deployment, CI/CD | M5 (Shield) | ... |

### API Endpoints (fill as you build)
| Method | Endpoint | Description | Owner | Status |
|--------|----------|-------------|-------|--------|
| GET | `/api/...` | ... | M4 | ⬜ |
| POST | `/api/...` | ... | M4 | ⬜ |
| PUT | `/api/...` | ... | M4 | ⬜ |
| DELETE | `/api/...` | ... | M4 | ⬜ |

### Database Schema (fill as you build)
```
Table: ...
─────────────
- id (PK)
- ...
- created_at
- updated_at

Table: ...
─────────────
- id (PK)
- ...
- foreign_key (FK → ...)
```

---

## 🛠️ 4. Tech Stack Decision

> Fill this in during Phase 1 (Hour 0–2). Choose what the team knows best — this is NOT the time to learn new tech.

| Layer | Technology | Why |
|-------|-----------|-----|
| **Frontend** | _e.g., React / Vue / Vanilla JS / HTML+CSS_ | ... |
| **Backend** | _e.g., Node.js / Python Flask / FastAPI / Express_ | ... |
| **Database** | _e.g., SQLite / MongoDB / PostgreSQL / Firebase_ | ... |
| **Deployment** | _e.g., Vercel / Railway / Render / Netlify_ | ... |
| **Version Control** | GitHub | Required by rules |
| **Design Tool** | _e.g., Excalidraw / draw.io_ | For system design diagram |

---

## 📊 5. Feature Ownership & Progress Tracker

### Member Assignment
| Member | Role | Owns Features | Current Task | Status |
|--------|------|---------------|-------------|--------|
| M1 (Captain) | Team Lead / Architect | Architecture, F?, F? | ... | 🟢 Active |
| M2 (Engine) | Backend Lead | F?, F? | ... | 🟢 Active |
| M3 (Pixel) | Frontend Lead | All UI screens | ... | 🟢 Active |
| M4 (Bridge) | Integration / API | API layer, F? | ... | 🟢 Active |
| M5 (Shield) | QA / DevOps / Docs | Testing, Deploy, README | ... | 🟢 Active |

### Feature Progress
| Feature | Owner | Hour Started | Hour Completed | Works? | Edge Cases? | Notes |
|---------|-------|-------------|----------------|--------|-------------|-------|
| F1: ... | | | | ⬜ | ⬜ | |
| F2: ... | | | | ⬜ | ⬜ | |
| F3: ... | | | | ⬜ | ⬜ | |
| F4: ... | | | | ⬜ | ⬜ | |
| F5: ... | | | | ⬜ | ⬜ | |

---

## 🔴 6. Judging Rounds — Preparation Guide

### Round 1 — Hour 7 (5:00 PM, April 18)
**What judges evaluate**: System Design Diagram + Initial Progress

| Deliverable | Status | Notes |
|------------|--------|-------|
| System Design Diagram (clean, readable) | ⬜ | Must be ready by Hour 5 |
| Working demo of core flow (happy path) | ⬜ | Input → Process → Output |
| Clear verbal explanation of architecture | ⬜ | M1 leads, all support |
| Each member explains their component | ⬜ | Practice at Hour 6 |

**Demo Script for Round 1:**
1. _"Our project is _________ which solves _________ by _________."_
2. _Show the system design diagram and explain each component._
3. _Demo the core flow: [describe steps]._
4. _"By the next round, we will have completed: _________."_

---

### Round 2 — Hour 14 (12:00 AM, April 19)
**What judges evaluate**: Working Progress — All Major Features

| Deliverable | Status | Notes |
|------------|--------|-------|
| All major features working | ⬜ | Every requirement |
| Edge cases handled for core flow | ⬜ | Empty, invalid, large |
| End-to-end flow without manual steps | ⬜ | Judges run it themselves |
| No crashes during demo | ⬜ | Test before presenting |

**Demo Script for Round 2:**
1. _"Since Round 1, we've completed: _________."_
2. _Full demo: walk through EVERY feature._
3. _Show edge case handling: [empty input, invalid data]._
4. _"For the final round, we're focusing on: _________."_

---

### Round 3 — Hour 23 (9:00 AM, April 19)
**What judges evaluate**: Near-Final Product — Everything End-to-End

| Deliverable | Status | Notes |
|------------|--------|-------|
| Complete, polished product | ⬜ | All features, all edges |
| Deployed and accessible | ⬜ | Live link or video |
| Demo video recorded (backup) | ⬜ | 3-5 minutes |
| README complete with setup guide | ⬜ | Judges follow this |
| All AI tools disclosed | ⬜ | Mandatory |

**Demo Script for Round 3:**
1. _"Our project _________ is a complete solution for _________."_
2. _Full polished demo covering ALL features._
3. _"Key technical decisions: _________."_
4. _"Edge cases we handle: _________."_
5. _"Our tech stack is _________ and here's why: _________."_

---

## ❓ 7. Judge Q&A Preparation

> Judges score on **80% Functional Correctness + 20% Completeness**. Their questions will probe whether your solution ACTUALLY works and covers ALL requirements.

### 🔴 Category 1: Functional Correctness (80% of score)

These questions test if your solution WORKS correctly:

| # | Expected Question | How to Answer | Who Answers |
|---|------------------|---------------|-------------|
| 1 | **"Walk me through the complete flow from start to finish."** | Demo the full happy path: user input → processing → result. Show it live, not slides. | M1 (Captain) |
| 2 | **"What happens if I enter invalid/empty input?"** | Show the validation. Enter empty form, garbage data, SQL injection-style strings. It should NOT crash. | M3 (Pixel) |
| 3 | **"Can I run this on my machine? How?"** | Point to README. Walk through: `git clone` → `npm install` → `npm start`. It must work in < 5 commands. | M5 (Shield) |
| 4 | **"What happens when [edge case]?"** | Demonstrate the edge case live. Show the error handling. "We anticipated this — here's how we handle it." | M2 (Engine) |
| 5 | **"Is the output deterministic? Run it twice with the same input."** | Run the same input twice. Show identical output. No randomness in core logic. | M2 (Engine) |
| 6 | **"Does this work without any manual database/server setup?"** | Show the one-command setup. No manual DB creation, no env file editing, no seed scripts. | M5 (Shield) |
| 7 | **"What if the network goes down / API fails?"** | Show fallback behavior: cached data, retry logic, or clear error message. No silent failures. | M4 (Bridge) |
| 8 | **"Show me feature X that was in the problem statement."** | Navigate directly to it. If not implemented, be honest: "We prioritized X, Y, Z first because they were core." | Owner of X |

### 🟡 Category 2: Completeness (20% of score)

These questions check if you covered ALL requirements:

| # | Expected Question | How to Answer | Who Answers |
|---|------------------|---------------|-------------|
| 9 | **"Did you implement all the requirements?"** | Pull up the requirement checklist. Walk through each one with a live demo. | M1 (Captain) |
| 10 | **"What's missing?"** | Be honest. "Everything in the core spec is done. As stretch goals, we were working on X." | M1 (Captain) |
| 11 | **"Why did you prioritize these features over others?"** | "We prioritized based on the scoring rubric — functional correctness first, then completeness." | M1 (Captain) |

### 🟠 Category 3: Technical Depth (Grilling)

These probe whether you UNDERSTAND your code:

| # | Expected Question | How to Answer | Who Answers |
|---|------------------|---------------|-------------|
| 12 | **"Explain this piece of code. What does it do?"** | Walk through line-by-line. Explain the WHY, not just the WHAT. | Owner of that code |
| 13 | **"Why did you choose [tech/framework]?"** | "We chose X because [team familiarity / best fit for the problem / performance]. We considered Y but Z." | M1 (Captain) |
| 14 | **"What AI tools did you use?"** | Be completely transparent. "We used Copilot for boilerplate, ChatGPT for debugging. All code was reviewed and understood by the team." | M5 (Shield) |
| 15 | **"What would you change with more time?"** | Have 2-3 honest improvements ready: "Better error handling in X, add caching for Y, improve UI for Z." | M1 (Captain) |
| 16 | **"How does [member name] contribute? Explain your part."** | Each member must explain their component confidently. Inability to explain = score penalty. | Each member |
| 17 | **"What was the hardest technical challenge?"** | Pick a real challenge you solved. Explain the problem, what you tried, and how you solved it. | Whoever solved it |

### 🔵 Category 4: Architecture & Design

| # | Expected Question | How to Answer | Who Answers |
|---|------------------|---------------|-------------|
| 18 | **"Walk me through your system design."** | Use the diagram. Explain each component, how they connect, and data flow. | M1 (Captain) |
| 19 | **"Why this architecture?"** | "This architecture separates concerns — frontend handles UI, backend handles logic, API layer manages communication. This lets us work in parallel and test independently." | M1 (Captain) |
| 20 | **"How does data flow through your system?"** | Trace a request: "User clicks submit → frontend validates → POST to /api/X → backend processes → stores in DB → returns response → frontend displays." | M4 (Bridge) |

### 💡 Golden Rules for Answering Judges

> [!IMPORTANT]
> 1. **NEVER say "it should work"** — demo it LIVE or don't claim it
> 2. **NEVER blame the tools** — "React was slow" is not an answer
> 3. **Be honest about gaps** — "We didn't implement X, here's why" > pretending it works
> 4. **Every member speaks** — if one person answers everything, judges suspect the others didn't contribute
> 5. **Show, don't tell** — demo beats slides. Always demo live if possible
> 6. **Keep answers SHORT** — 30 seconds max per answer. Judges have many teams to evaluate

---

## 📋 8. Hourly Progress Log

> Update this every hour. This is your war diary.

| Hour | Time | What Was Accomplished | Blockers | Next Priority |
|------|------|----------------------|----------|--------------|
| 0 | 10:00 AM | Problem statement received. Reading. | — | Understand requirements |
| 1 | 11:00 AM | | | |
| 2 | 12:00 PM | | | |
| 3 | 1:00 PM | | | |
| 4 | 2:00 PM | _LUNCH BREAK_ | | |
| 5 | 3:00 PM | | | |
| 6 | 4:00 PM | | | |
| 7 | 5:00 PM | **🔴 ROUND 1 JUDGING** | | |
| 8 | 6:00 PM | | | |
| 9 | 7:00 PM | | | |
| 10 | 8:00 PM | | | |
| 11 | 9:00 PM | _DINNER BREAK_ | | |
| 12 | 10:00 PM | | | |
| 13 | 11:00 PM | | | |
| 14 | 12:00 AM | **🔴 ROUND 2 JUDGING** | | |
| 15 | 1:00 AM | | | |
| 16 | 2:00 AM | | | |
| 17 | 3:00 AM | | | |
| 18 | 4:00 AM | | | |
| 19 | 5:00 AM | | | |
| 20 | 6:00 AM | | | |
| 21 | 7:00 AM | | | |
| 22 | 8:00 AM | **CODE FREEZE** | | |
| 23 | 9:00 AM | **🔴 ROUND 3 JUDGING** | | |
| 24 | 10:00 AM | **⏹ SUBMISSIONS DUE** | | |

---

## 🐛 9. Bug Tracker

| # | Bug Description | Severity | Found By | Assigned To | Status | Fixed? |
|---|----------------|----------|----------|-------------|--------|--------|
| B1 | | 🔴 Critical | | | | ⬜ |
| B2 | | 🟡 Medium | | | | ⬜ |
| B3 | | 🟢 Low | | | | ⬜ |

> **Severity Guide**: 🔴 Critical = App crashes/breaks core flow. 🟡 Medium = Feature doesn't work but app runs. 🟢 Low = Visual/minor issue.

---

## 🤖 10. AI Tools Disclosure Log

> **MANDATORY**: List EVERY AI tool used. Failure to disclose = disqualification risk.

| AI Tool | Used By | What For | Code Section |
|---------|---------|----------|-------------|
| GitHub Copilot | | | |
| ChatGPT | | | |
| Claude | | | |
| Gemini | | | |
| _Other_ | | | |

---

## 📦 11. Submission Checklist

> **Deadline: 9:30 AM April 19** (30-min buffer before 10:00 AM hard deadline)

### Pre-Submission (Hour 22-23)
- [ ] All code committed and pushed to GitHub
- [ ] Repo is **public** or judges have access
- [ ] `README.md` is complete with:
  - [ ] Project title + one-line description
  - [ ] Tech stack listed
  - [ ] Step-by-step setup instructions (must work on judge's machine)
  - [ ] ALL AI tools disclosed
  - [ ] Screenshots / demo GIF (optional but nice)
- [ ] All commits are timestamped **within 10:00 AM Apr 18 – 10:00 AM Apr 19**
- [ ] No credentials / API keys in the repo

### Submission Materials
- [ ] **Project title** + one-line description
- [ ] **Track selection** confirmed (Web3 / Others)
- [ ] **GitHub repo link** — verified accessible
- [ ] **Working demo** — deployed link OR video walkthrough
- [ ] **Demo video** (3–5 min) — recorded and uploaded
- [ ] **Presentation deck** (5–10 slides) — Problem, Solution, Demo, Future Scope

### Final Verification
- [ ] Submitted through **official portal** ✅
- [ ] Portal shows submission as **confirmed** ✅
- [ ] Tested deployed version works ✅
- [ ] Can `git clone` and run from scratch ✅

---

## ⚡ Quick Reference

```
┌───────────────────────────────────────────────┐
│          DevClash 2026 — Quick Ref            │
├───────────────────────────────────────────────┤
│                                               │
│  SCORING:  80% Correctness + 20% Complete     │
│                                               │
│  PRIORITY:                                    │
│    1. Make it WORK  (correctness)             │
│    2. Make it COMPLETE  (all features)        │
│    3. Make it PRETTY  (only if time)          │
│                                               │
│  ROUNDS:                                      │
│    R1 → 5 PM  (Architecture + Core Demo)      │
│    R2 → 12 AM (All Features Working)          │
│    R3 → 9 AM  (Final Polished Product)        │
│                                               │
│  SUBMIT BY: 9:30 AM Apr 19                    │
│  CODE FREEZE: 8:00 AM Apr 19                  │
│                                               │
│  ⚠️ NO pre-event commits                     │
│  ⚠️ Disclose ALL AI tools                    │
│  ⚠️ Every member must explain their code     │
└───────────────────────────────────────────────┘
```

---

_Last updated: April 18, 2026 — Awaiting problem statement reveal at 10:00 AM_
