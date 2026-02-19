# 🚀 ContractClarity - 对簿AI

### AI-Powered Deep Contract Risk Intelligence Engine

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue?style=for-the-badge&logo=python " />
  <img src="https://img.shields.io/badge/Flask-Backend-black?style=for-the-badge&logo=flask " />
  <img src="https://img.shields.io/badge/LLM-DeepSeek-red?style=for-the-badge " />
  <img src="https://img.shields.io/badge/VectorDB-Chroma-green?style=for-the-badge " />
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge " />
</p>

---

## 📖 Overview

**ContractClarity** is an AI-driven legal contract analysis engine that performs:

* Deep structural risk auditing
* Law-grounded clause validation
* Quantitative risk scoring
* Negotiation strategy generation
* Multi-style persuasion scripting

It combines:

* 🔍 Retrieval-Augmented Generation (RAG)
* 📚 Domain-specific legal vector databases
* 🧠 Multi-stage LLM reasoning
* ⚖️ Structured legal intelligence output

Designed as a practical AI LegalTech system rather than a demo chatbot.

---

## 🖥 Product Interface

### 🏠 Contract Input Interface

<p align="center">
  <img src="assets/demo_home.png" width="800">
</p>

Users paste contract content and select a contract category.

---

### 🔎 Risk Analysis Dashboard

<p align="center">
  <img src="assets/demo_analysis.png" width="800">
</p>

The system returns:

* Contract type classification
* Jurisdiction inference
* Overall risk level
* Quantified risk score (0–100)
* 5–7 core high-risk issues
* Legal references
* Defensive revision suggestions

---

### ✉️ AI Negotiation Strategy Generator

<p align="center">
  <img src="assets/demo_negotiation.png" width="800">
</p>

Automatically generates:

* 500+ word professional negotiation email
* Structured persuasion script
* Aggressive / Consultative / Compromise strategy styles

---

## 🧠 System Architecture

<p align="center">
  <img src="assets/architecture.png" width="700">
</p>

**Pipeline Flow**

1. User submits contract
2. Flask API creates async task
3. Relevant laws retrieved from Chroma vector database
4. DeepSeek LLM performs:

   * Risk auditing
   * Legal grounding
   * Negotiation planning
5. Structured JSON response returned

---

## 🧱 Project Structure

```bash
ContractClarity/
│
├── backend/
│   ├── app.py              # Core analysis engine
│   ├── ingest.py           # Legal corpus vectorization
│   └── .env.example
│
├── frontend/
│   └── index.html
│
├── laws/
│   └── 法律条文/
│
├── assets/
│   ├── demo_home.png
│   ├── demo_analysis.png
│   ├── demo_negotiation.png
│   └── architecture.png
│
├── requirements.txt
└── README.md
```
System Architecture Diagram:
```
User
  ↓
Frontend (index.html)
  ↓
Flask/FastAPI Backend (app.py)
  ↓
Category Router
  ↓
Chroma Vector DB (per category)
  ↓
HuggingFace Embeddings (bge-large-zh-v1.5)
  ↓
LLM (Chat Model)
  ↓
Answer + Cited Legal Articles
```

---

## ⚙️ Installation

### 1️⃣ Clone the repository

```bash
git clone https://github.com/yourusername/ContractClarity.git 
cd ContractClarity
```

---

### 2️⃣ Install dependencies

```bash
pip install -r requirements.txt
```

---

### 3️⃣ Configure environment variables

Create `.env` inside `/backend/`:

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

### 5️⃣ Run Backend Server

```bash
python app.py
```

Runs on:

```
http://localhost:5000
```

---

## 🔌 API Endpoints

### POST `/analyze`

```json
{
  "text": "contract content",
  "category": "劳动用工类"
}
```

Returns:

```json
{
  "task_id": "uuid"
}
```

---

### GET `/status/<task_id>`

Returns analysis result or progress state.

---

## 🎯 Core Features

### 🔍 Deep Risk Detection

* Identifies hidden liability asymmetry
* Detects clause omissions
* Flags regulatory violations

---

### ⚖️ Law-Grounded Intelligence

Retrieves relevant legal references from:

* Categorized Chinese legal corpus
* Vector similarity search
* Embedding model: BAAI/bge-large-zh-v1.5

---

### 📊 Structured Risk Quantification

Generates:

* overallRisk
* riskScore (0–100)
* severity classification

---

### 🤝 AI Negotiation Co-Pilot

Generates:

* Professional negotiation email (500+ words)
* Strategic persuasion scripts
* Multi-style negotiation approaches

---

## 🚀 Future Improvements

* Support multi-jurisdiction legal systems
* Add PDF contract parsing
* Deploy Dockerized version
* Add user authentication layer
* Frontend upgrade to React

---

## 📄 License

This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.

---
