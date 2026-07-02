import os
import json
from datetime import datetime
from Finance_tool.crew import FinanceCrew

def run():
    finance_crew = FinanceCrew()

    # Laad JSON input
    json_path = os.path.join(os.path.dirname(__file__), 'user_inputs.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        user_data = json.load(f)


    inputs = {
        'user_input': json.dumps(user_data, indent=2),
        'current_date': datetime.now().strftime("%Y-%m-%d")
    }

    finance_crew.crew().kickoff(inputs=inputs)

if __name__ == "__main__":
    run()