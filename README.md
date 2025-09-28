# TalentFitAI

A full-stack AI-driven application to assist in recruitment — parsing job descriptions, matching candidates, and generating interview/assessment content.

## Table of Contents

* [Overview](#overview)
* [Features](#features)
* [Tech Stack & Architecture](#tech-stack--architecture)
* [Getting Started](#getting-started)

  * [Prerequisites](#prerequisites)
  * [Installation](#installation)
  * [Running the App](#running-the-app)
* [Usage](#usage)
* [Project Structure](#project-structure)
* [Contributing](#contributing)
* [License](#license)
* [Contact](#contact)

## Overview

TalentFitAI is designed to streamline and enhance recruitment workflows using AI. It provides:

* Automated analysis of job descriptions (JDs)
* Candidate-to-job matching & scoring
* AI-generated interview questions, assessment suggestions, and reports
* A web UI for seamless interaction between users and the AI backend

## Features

* Parse and extract key skills, responsibilities, and requirements from JDs
* Score and rank candidate profiles against job criteria
* Generate tailored interview questions or assessment tasks
* Interactive web interface for recruiters or hiring managers
* Modular design to add new AI or matching modules

## Tech Stack & Architecture

* **Backend**: Python (Flask, FastAPI, or your chosen framework)
* **Frontend**: JavaScript/TypeScript (React, Vue, or similar)
* **LLM / AI modules**: custom components in `src/langgraphagenticai`
* **Other**:

  * `requirements.txt` for Python dependencies
  * `.env` file for configuration and secrets
  * Static files like `index.html` for landing pages

## Getting Started

### Prerequisites

* Python 3.8+
* Node.js & npm / yarn
* Git

### Installation

Clone the repository:

```bash
git clone https://github.com/adithyajalluri2005/TalentFitAI.git
cd TalentFitAI
```

#### Backend Setup

```bash
python -m venv venv
# On Windows:
venv\Scripts\activate  
# On macOS / Linux:
source venv/bin/activate

pip install -r requirements.txt
```

#### Frontend Setup

```bash
cd frontend
npm install     # or yarn install
```

## Running the App

### Backend (in the root folder)

```bash
# If using FastAPI / uvicorn
uvicorn app:app --reload

# Or if your app.py uses Flask or equivalent
python app.py
```

### Frontend

```bash
cd frontend
npm run dev     # or yarn dev
```

Visit [http://localhost:3000](http://localhost:3000) (or whichever port your frontend serves) in your browser to access the UI.

## Usage

1. Upload or input a job description
2. The system analyzes and structures the JD
3. Input a candidate’s profile for matching
4. Receive match scores, recommended interview questions, and assessment suggestions
5. View reports or export results

You may later augment this section with sample API calls, screenshots, or usage examples.

## Project Structure

```
TalentFitAI/
│
├── frontend/                   # Frontend UI code
├── src/                        # Backend / AI modules
│   └── langgraphagenticai/
│       ├── LLMS/
│       ├── graph/
│       ├── nodes/
│       ├── state/
│       └── tools/
├── app.py                      # Main backend entrypoint
├── requirements.txt            # Backend dependencies
├── .gitignore
├── .env                        # Environment / secrets
└── README.md                   # Project README (this file)
```

## Contributing

Contributions are welcome! Here’s how to get started:

1. Fork the repo
2. Create a branch:

   ```bash
   git checkout -b feature/your-feature
   ```
3. Make changes and commit:

   ```bash
   git commit -m "Add …"
   ```
4. Push your branch:

   ```bash
   git push origin feature/your-feature
   ```
5. Open a Pull Request

Please ensure your changes are documented, tested where feasible, and follow code/style conventions.

## License

This project is licensed under the **MIT License**.
(Include a `LICENSE` file in your repo with the full text.)

## Contact

Built by **Adithya Jalluri**
Feel free to reach out with questions, feedback, or collaboration ideas.
