# thesis_mas_financial_advice
Repository for the bachelor thesis by Jesper Duijn

# Thesis Code: Multi-Agent Financial Report Generator

This repository contains the code for my bachelor's thesis project. Because I just uploaded the files directly to share them for grading, the original folder structure has been flattened, but all the necessary logic and configuration files are here.

## What's in these files?

* **`app.py`** 
  The Streamlit website code. This handles the user questionnaire, does the hard-coded fiscal pre-calculations (to prevent LLM math errors), and calls the CrewAI logic.

* **`crew.py`** 
  The core CrewAI backend. This script sets up the Multi-Agent System, initializes the OpenAI model, and runs the four domain experts and the final editor.

* **`agents.yaml` & `tasks.yaml` in the config folder** 
  The configuration files that define the roles, goals, backstories, and specific tasks for each of the five AI agents.

* **Knowledge files (Markdown) in the knowledge folder** 
  These files contain the 2026 Dutch tax rules, Nibud guidelines, and other fiscal legislation that gets injected into the agents' context to keep them accurate.

* **Template files in the templates folder** 
  The formatting templates the agents are forced to use so the final report looks consistent.

* **`requirements.txt`** 
  The list of Python libraries needed for the project.

