# 🎤 P.R.I.S.M. — The Ultimate Winning Pitch

> **How to use this document:** Don't just read it. Use the bolded phrases as your vocal emphasis points. Look the judges right in the eye when you hit the "Wow Factors." 

---

## 1. THE HOOK (The Problem) — *[0:00 - 0:45]*

**"Every academic institution in the world is fighting a losing battle."**

Right now, tools like Turnitin rely on *Lexical Matching*. They scan a paper and ask a simple question: *"Has this exact sentence been published before?"* 

But modern plagiarism isn't copy-paste. It's **Stitched Plagiarism**. A student takes a paragraph from a 2018 Arxiv paper, translates it to French, translates it back to English, uses ChatGPT to paraphrase it, and splices it into their own work. 

Lexical matchers look at that and say: *0% Plagiarism. Clean paper.* 

They fail because they are looking at **WHAT** is written. They completely ignore **HOW** it is written. 

---

## 2. THE SOLUTION (Our Approach) — *[0:45 - 1:30]*

That’s why we built **P.R.I.S.M.** — Plagiarism Recognition via Integrated Stylometric Mapping. 

Rather than looking for copied words, P.R.I.S.M. analyzes **academic fingerprints**. 
Every author has a subconscious writing style. We don't care about the topic; we care about the structure. Do they use short, punchy sentences? What is their ratio of passive voice? What is their lexical richness, proved mathematically by Yule's K? 

When a student stitches someone else's work into their own, those subconscious metrics shift dramatically. P.R.I.S.M. mathematically detects that stylistic whiplash, flags the exact boundary where the transition occurred, and then provides undeniable evidence.

---

## 3. THE ARCHITECTURE (What's New & The "Hybrid" Edge) — *[1:30 - 2:30]*

If we just threw this at GPT-4 and asked, *"Did someone else write this?"*, that would be non-deterministic. It’s unprovable. You can't accuse a student just because "the AI said so."

Instead, we built a **Hybrid Dual-Engine Architecture**: 
Math provides the *proof*. AI provides the *explanation*.

**Stage 1: The Deterministic Math**
We use **spaCy** to extract 7 content-independent linguistic features per paragraph. We feed that matrix into an unsupervised clustering algorithm called **HDBSCAN**. Why HDBSCAN and not K-Means? Because HDBSCAN doesn't require us to guess how many authors there are. It automatically reads the data density, clusters the main author, and isolates ANY anomalous paragraph directly into a "Noise Cluster." 

**Stage 2: The AI Reasoning**
Only after the math mathematically proves an anomaly exists, we deploy **GPT-4o-mini** on those exact paragraphs. But we don't ask it *if* it's plagiarized. We ask it to act as a Forensic Linguist and *explain in natural language* why the mathematical shift occurred. 

We combine the concrete proof of Python with the human readability of an LLM.

---

## 4. THE WOW FACTORS (Winning Their Hearts) — *[2:30 - 3:30]*

*When presenting these, slow down. These are the technical flexes.*

**Wow Factor 1: Temporal Citation Forensics**
We built a deterministic regex engine that pulls every academic citation. If HDBSCAN flags a paragraph as an anomaly, we check the median publication year of its citations. If a 2024 paper suddenly has one paragraph exclusively citing literature from 1996, that’s a **temporal anomaly**. We catch people accidentally bringing the bibliography of the paper they stole.

**Wow Factor 2: Local Semantic Source Tracing**
We don't stop at telling you it's stolen; we find the original paper. We run `spaCy` to extract noun chunks from the stolen paragraph, query the **Arxiv API**, and generate 384-dimensional embeddings using a **Local MiniLM model running instantly on our CPU**. We do cosine similarity matching on the fly without making a single OpenAI embedding API call. It's fast, free, and resilient.

**Wow Factor 3: Total Fallback Chain**
If OpenAI's servers crash during this hackathon, our entire math layer, our clustering, our heatmap dashboard, our citation forensics, and our local source tracing **still work completely offline.** We built an enterprise-grade fallback chain.

---

## 5. THE CLOSING (The Impact) — *[3:30 - 4:00]*

P.R.I.S.M. is not just an AI wrapper. It is a **forensic-grade, prosecutable evidence engine**. 

We don't give professors a black-box percentage. We give them a dashboard that says: 
*"Paragraph 9 is anomalous. The math shows the lexical richness dropped by 43%. The AI notes a shift from active to passive voice. The citations are 15 years out of temporal bounds. And here is the link to the original Arxiv paper it was stolen from with 87% cosine similarity."*

That is how you restore academic integrity. Thank you.

---

## 💡 Quick Tips for Q&A

1. **If they ask why not Turnitin:** "Turnitin is a massive dictionary lookup. P.R.I.S.M. is behavioral analysis."
2. **If they ask about Cost:** "Because HDBSCAN acts as a gatekeeper, we only send the 5% of text that is anomalous to GPT-4. Processing a 20-page paper costs less than $0.05."
3. **If they ask about False Positives (e.g. Co-authors):** "It's designed to detect stitched boundaries, not just multiple authors. If two authors co-write cleanly, their styles harmonize. Our `min_cluster_size` prevents flagging normal variations."
