# 🚀 ContractClarity — 对簿AI

### AI-Powered Deep Contract Risk Intelligence Engine

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue?style=for-the-badge&logo=python" />
  <img src="https://img.shields.io/badge/Flask-Backend-black?style=for-the-badge&logo=flask" />
  <img src="https://img.shields.io/badge/LLM-DeepSeek-red?style=for-the-badge" />
  <img src="https://img.shields.io/badge/VectorDB-Chroma-green?style=for-the-badge" />
  <img src="https://img.shields.io/badge/RAG-Legal%20Reasoning-purple?style=for-the-badge" />
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" />
</p>

---

## 📖 Overview

**ContractClarity** is a production-oriented AI LegalTech system designed to perform deep contract risk intelligence rather than simple surface-level clause summarization.

It integrates:

* 🔍 Retrieval-Augmented Generation (RAG)
* 📚 Domain-specific legal vector database
* 🧠 Multi-stage LLM reasoning
* ⚖️ Structured legal-grounded analysis
* 🤝 Negotiation strategy automation

This system moves beyond “chatbot-style contract explanation” and delivers structured legal risk intelligence, quantitative scoring, and strategic negotiation guidance.


---


## 🖥 Product Interface

---

### 🔐 Authentication & Entry

<p align="center">
  <img src="assets/contract-review-homepage.png" width="48%">
  <img src="assets/login-modal-verification-code.png" width="48%">
</p>

Users securely access the platform via verification-code login.
The homepage introduces the AI-powered contract intelligence workflow.

---

### 📂 Contract Type Selection

<p align="center">
  <img src="assets/contract-type-selection-english.png" width="48%">
  <img src="assets/contract-type-details-expanded.png" width="48%">
</p>

Users select the appropriate contract category to activate specialized legal knowledge routing.

---

### 📄 Contract Upload & Submission

<p align="center">
  <img src="assets/contract-upload-page.png" width="900">
</p>

Supports structured contract upload and text-based submission.

---

### ⚙️ AI Review Processing

<p align="center">
  <img src="assets/ai-review-processing.png" width="900">
</p>

The system performs:

* Legal retrieval (RAG)
* Clause-level semantic parsing
* Multi-stage risk reasoning
* Quantitative scoring

---

## 🔎 Risk Intelligence Dashboard

---

### 📊 Overall Risk Overview

<p align="center">
  <img src="assets/risk-overview-report.png" width="900">
</p>

Provides:

* Risk severity level
* Risk score (0–100)
* Core high-risk factors
* Legal basis references

---

### 📝 Contract Risk Highlighting

<p align="center">
  <img src="assets/contract-text-with-risk-highlights.png" width="900">
</p>

Clause-level risk highlighting directly inside the contract body.

---

### 🔬 Deep Risk Detail Analysis

<p align="center">
  <img src="assets/risk-detail-analysis-1.png" width="48%">
  <img src="assets/risk-detail-analysis-2.png" width="48%">
</p>

Each high-risk issue includes:

* Legal interpretation
* Liability explanation
* Practical impact
* Mitigation suggestions

---

## ✉️ AI Negotiation Strategy Generator

---

### 📞 Phone Script & Multi-Style Strategy

<p align="center">
  <img src="assets/negotiation-strategy-phone-script.png" width="48%">
  <img src="assets/negotiation-strategy-multiple-styles.png" width="48%">
</p>

Automatically generates:

* Structured negotiation talking points
* Aggressive / Consultative / Compromise styles

---

### 📧 Written Communication Templates

<p align="center">
  <img src="assets/written-communication-email-template.png" width="900">
</p>

Produces 500+ word professional negotiation emails grounded in legal reasoning.

---

## 🛠 Contract Revision Engine

---

### 📜 Full Contract Revision

<p align="center">
  <img src="assets/contract-revision-full-text.png" width="48%">
  <img src="assets/contract-revision-notes.png" width="48%">
</p>

Provides:

* Full revised contract draft
* Inline modification notes
* Risk-justified adjustments

---

## 📁 User Dashboard & Archive

---

### 🧾 Contract Management System

<p align="center">
  <img src="assets/user-dashboard-overview.png" width="48%">
  <img src="assets/user-contract-archive-detail.png" width="48%">
</p>

Includes:

* Historical contract archive
* Review status tracking
* Risk score comparison
* Structured report retrieval

---

## 🧠 System Architecture

<p align="center">
  <img src="assets/System Architecture Diagram.png" width="850">
</p>

### Pipeline Flow

```
User Input
   ↓
Frontend (HTML UI)
   ↓
Flask Backend (app.py)
   ↓
Category Router
   ↓
Chroma Vector DB (Legal Corpus)
   ↓
Embedding Model (bge-large-zh-v1.5)
   ↓
DeepSeek LLM
   ↓
Structured JSON Response
```

---

## 🧱 Project Structure

```bash
ContractClarity/
│
├── backend/
│   ├── app.py                # Core Flask API
│   ├── ingest.py             # Legal corpus vectorization
│   ├── .env.example
│
├── frontend/
│   └── index.html            # UI Interface
│
├── data/
│   └── 法律条文/   # Categorized legal documents
│
├── assets/...
│
├── requirements.txt
├── README.md
└── LICENSE
```

---

## ⚙️ Installation

### 1️⃣ Clone Repository

```bash
git clone https://github.com/yourusername/ContractClarity.git
cd ContractClarity
```

---

### 2️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 3️⃣ Configure Environment Variables

Create:

```
backend/.env
```

Add:

```env
DEEPSEEK_API_KEY=your_api_key_here
```

---

### 4️⃣ Build Legal Vector Database

```bash
cd backend
python ingest.py
```

---

### 5️⃣ Run Server

```bash
python app.py
```

Server runs at:

```
http://localhost:5000
```

---

## 🔌 API Endpoints

### POST `/analyze`

Request:

```json
{
  "text": "contract content",
  "category": "劳动用工类"
}
```

Response:

```json
{
  "task_id": "uuid"
}
```

---

### GET `/status/<task_id>`

Returns:

```json
{
  "status": "completed",
  "overallRisk": "High",
  "riskScore": 82,
  "issues": [...]
}
```

---

## 🎯 Core Capabilities

### 🔍 Deep Structural Risk Auditing

* Liability asymmetry detection
* Missing clause identification
* Regulatory compliance checks

---

### ⚖️ Law-Grounded Retrieval

* Category-based vector search
* Embedding model: `BAAI/bge-large-zh-v1.5`
* Similarity-based legal citation

---

### 📊 Quantitative Risk Scoring

Produces:

* `overallRisk`
* `riskScore`
* Severity breakdown

---

### 🤝 AI Negotiation Co-Pilot

Generates:

* Formal legal emails
* Strategic persuasion scripts
* Multi-style negotiation pathways

---

## 🚀 Future Roadmap

* Multi-jurisdiction legal system support
* PDF & DOCX contract ingestion
* Docker deployment
* Frontend migration to React
* User authentication system
* SaaS deployment version

---

## 📌 Design Philosophy

ContractClarity is built under three principles:

1. Legal grounding over hallucinated reasoning
2. Structured output over verbose text
3. Practical negotiation utility over abstract explanation

---

## 📄 License

This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.

---
