import os
import streamlit as st
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task, before_kickoff
from crewai.knowledge.source.text_file_knowledge_source import TextFileKnowledgeSource


# Google Gemini 
# Flash
gemini_llm_fast = LLM(
    model="gemini/gemini-3.5-flash",
    api_key=st.secrets.get("GEMINI_API_KEY", "GEEN_KEY_GEVONDEN"),
    kwargs={
        "safety_settings": [
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"}
        ]
    }
)

# Flash
gemini_llm_smart = LLM(
    model="gemini/gemini-3.1-pro-preview",
    api_key=st.secrets.get("GEMINI_API_KEY", "GEEN_KEY_GEVONDEN"),
    kwargs={
        "safety_settings": [
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"}
        ]
    }
)

# OpenAI
# Mini 
openai_llm_fast = LLM(
    model="gpt-5.4-mini", 
    api_key=st.secrets.get("OPENAI_API_KEY", "GEEN_KEY_GEVONDEN")
)

# 5.5
openai_llm_smart = LLM(
    model="gpt-5.5", 
    api_key=st.secrets.get("OPENAI_API_KEY", "GEEN_KEY_GEVONDEN")
)

# Anthropic Claude 
claude_llm = LLM(
    model="claude-opus-4-8",
    api_key=st.secrets.get("ANTHROPIC_API_KEY", "GEEN_KEY_GEVONDEN")
)

# LLM Keuze
FINAL_LLM = openai_llm_smart
DEEL_LLM = openai_llm_smart


# Class
@CrewBase
class FinanceCrew():
    """Volledig autonome Finance Crew voor Streamlit 2026"""

    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    def _read_file(self, folder, filename):
        """Interne helper om bestanden veilig te laden uit specifieke mappen."""
        base_path = os.path.join(os.getcwd(), folder, filename)
        try:
            with open(base_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return f"Waarschuwing: Bestand {filename} niet gevonden in {folder}."

    @before_kickoff
    def prepare_inputs(self, inputs):
        """
        Injecteert alle benodigde bronnen en templates in de inputs 
        vlak voordat de crew start.
        """
        # Inkomsten & Experts context
        inputs['inkomsten_context'] = self._read_file('knowledge', 'inkomen_toeslagen_fiscaliteit.md')
        inputs['ondernemen_context'] = self._read_file('knowledge', 'ondernemen_dga_mobiliteit.md')
        inputs['wonen_context'] = self._read_file('knowledge', 'wonen_vastgoed.md')
        inputs['vermogen_context'] = self._read_file('knowledge', 'vermogen_pensioen_estateplanning.md')
        
        # Specifieke strategie voor de Final Editor
        inputs['strategie_context'] = self._read_file('knowledge', 'strategie_budget_zorg.md')
        
        # Rapport template inladen
        inputs['report_template'] = self._read_file('templates', 'template1.md')

        inputs['inkomen_template'] = self._read_file('templates', 'inkomen_template.md')
        inputs['ondernemen_template'] = self._read_file('templates', 'ondernemen_template.md')
        inputs['wonen_template'] = self._read_file('templates', 'wonen_template.md')
        inputs['vermogen_template'] = self._read_file('templates', 'vermogen_template.md')

        
        return inputs

    # --- Agents ---

    @agent
    def inkomsten_expert(self) -> Agent:
        return Agent(config=self.agents_config['inkomsten_expert'], llm=DEEL_LLM, verbose=True)

    @agent
    def ondernemers_expert(self) -> Agent:
        return Agent(config=self.agents_config['ondernemers_expert'], llm=DEEL_LLM, verbose=True)

    @agent
    def wonen_expert(self) -> Agent:
        return Agent(config=self.agents_config['wonen_expert'], llm=DEEL_LLM, verbose=True)

    @agent
    def vermogens_expert(self) -> Agent:
        return Agent(config=self.agents_config['vermogens_expert'], llm=DEEL_LLM, verbose=True)

    @agent
    def final_editor(self) -> Agent:
        return Agent(config=self.agents_config['final_editor'], llm=FINAL_LLM, verbose=True)

    # --- Tasks ---

    @task
    def inkomsten_taak(self) -> Task:
        return Task(config=self.tasks_config['inkomsten_taak'], agent=self.inkomsten_expert(), async_execution=True, inject_date=True)

    @task
    def ondernemers_taak(self) -> Task:
        return Task(config=self.tasks_config['ondernemers_taak'], agent=self.ondernemers_expert(), async_execution=True, inject_date=True)

    @task
    def wonen_taak(self) -> Task:
        return Task(config=self.tasks_config['wonen_taak'], agent=self.wonen_expert(), async_execution=True, inject_date=True)

    @task
    def vermogens_taak(self) -> Task:
        return Task(config=self.tasks_config['vermogens_taak'], agent=self.vermogens_expert(), async_execution=True, inject_date=True)

    @task
    def report_generation_task(self) -> Task:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        bestandsnaam = f'reports/financial_report_{timestamp}.md'
        return Task(
            config=self.tasks_config['report_generation_task'],
            agent=self.final_editor(),
            context=[
                self.inkomsten_taak(),
                self.ondernemers_taak(),
                self.wonen_taak(),
                self.vermogens_taak()
            ],
            inject_date=True,
            output_file=bestandsnaam
        )

    # --- Crew ---
    @crew
    def crew(self) -> Crew:
        knowledge_source = TextFileKnowledgeSource(
            file_paths=[
                "inkomen_toeslagen_fiscaliteit.md",
                "ondernemen_dga_mobiliteit.md",
                "wonen_vastgoed.md",
                "vermogen_pensioen_estateplanning.md",
                "strategie_budget_zorg.md"
            ]
        )

        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            knowledge_sources=[knowledge_source],
        )